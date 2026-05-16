"""
Spark Job — WeeklyMLFeaturesJob
================================
Reads the previous 7 days of hourly aggregations from InfluxDB and computes
per-room weekly feature vectors for ML model training.

Triggered every Monday at 02:00 by weekly_features_dag.

Feature vectors (per room, per week):
    avg_occ_ratio     — mean occupancy ratio (occupancy / room_capacity)
    peak_occ_hour     — hour of day with highest average occupancy (0-23)
    avg_temp_c        — mean temperature in °C
    total_energy_kwh  — total energy consumption in kWh
    data_completeness — fraction of expected hourly windows with data (0-1)

Room capacity is loaded from PostgreSQL `rooms` table and joined with the
Spark DataFrame so the occupancy ratio can be computed correctly.

Output: PostgreSQL `ml_features` table (weekly upsert).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
from influxdb_client import InfluxDBClient
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from processing.spark.config import config
from processing.spark.utils import build_spark_session
from processing.spark.utils.postgres_writer import write_ml_features
from shared.db import get_db_connection

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Weekly ML features job")
    p.add_argument("--week-start", type=str, default=None,
                   help="Monday of the week to process YYYY-MM-DD. Defaults to last Monday.")
    return p.parse_args()


def _week_window(week_str: str | None) -> tuple[datetime, datetime]:
    if week_str:
        start = datetime.strptime(week_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # Previous Monday
        start = today - timedelta(days=today.weekday() + 7)
    return start, start + timedelta(days=7)


def _load_room_metadata() -> pd.DataFrame:
    """Load room_id → (building_id, room_type, capacity) from PostgreSQL."""
    conn = get_db_connection(config.database_url)
    df   = pd.read_sql(
        "SELECT id AS room_id, building_id, room_type, capacity FROM rooms", conn
    )
    conn.close()
    return df


def run(week_str: str | None = None) -> None:
    start, stop = _week_window(week_str)
    week_label  = start.strftime("%Y-%m-%d")
    logger.info(f"Computing ML features for week starting {week_label}")

    # ---------------------------------------------------------------------------
    # Read hourly aggregations for all sensor types for the week
    # ---------------------------------------------------------------------------
    start_rfc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc  = stop.strftime("%Y-%m-%dT%H:%M:%SZ")

    flux = f"""
from(bucket: "{config.influxdb_bucket_1h}")
  |> range(start: {start_rfc}, stop: {stop_rfc})
  |> filter(fn: (r) => r._measurement =~ /^sensor_1h_/)
  |> pivot(
       rowKey: ["_time", "building_id", "room_id", "sensor_type"],
       columnKey: ["_field"],
       valueColumn: "_value"
     )
  |> keep(columns: ["_time", "building_id", "room_id", "sensor_type",
                     "avg", "sum_avg", "total_count"])
"""

    client = InfluxDBClient(url=config.influxdb_url, token=config.influxdb_token, org=config.influxdb_org)
    try:
        pdf = client.query_api().query_data_frame(flux)
    finally:
        client.close()

    if isinstance(pdf, list):
        pdf = pd.concat(pdf, ignore_index=True) if pdf else pd.DataFrame()
    if pdf is None or pdf.empty:
        logger.warning(f"No data for week {week_label} — skipping")
        return

    rooms_pdf = _load_room_metadata()

    spark = build_spark_session("WeeklyMLFeatures")
    spark.sparkContext.setLogLevel("WARN")

    sdf   = spark.createDataFrame(pdf)
    rooms = spark.createDataFrame(rooms_pdf)

    # Expected number of hourly windows per room per week: 7 * 24 = 168
    EXPECTED_HOURS = 168

    # Temperature features
    temp_features = (
        sdf.filter(F.col("sensor_type") == "temperature")
        .groupBy("room_id")
        .agg(F.mean("avg").alias("avg_temp_c"))
    )

    # Energy features
    energy_features = (
        sdf.filter(F.col("sensor_type") == "energy")
        .groupBy("room_id")
        .agg(
            (F.sum("sum_avg") * 3600 / 1000).alias("total_energy_kwh"),
        )
    )

    # Occupancy features — requires room capacity join for ratio
    occ_sdf = sdf.filter(F.col("sensor_type") == "occupancy")
    occ_with_capacity = occ_sdf.join(rooms.select("room_id", "capacity"), on="room_id", how="left")

    # Peak occupancy hour: average occupancy by hour-of-day, find argmax
    occ_with_hour = occ_with_capacity.withColumn(
        "hour_of_day", F.hour(F.col("_time"))
    )
    occ_by_hour = occ_with_hour.groupBy("room_id", "hour_of_day").agg(
        F.mean("avg").alias("mean_occ")
    )
    window_spec = Window.partitionBy("room_id").orderBy(F.col("mean_occ").desc())
    peak_hour = (
        occ_by_hour
        .withColumn("rn", F.row_number().over(window_spec))
        .filter(F.col("rn") == 1)
        .select("room_id", F.col("hour_of_day").alias("peak_occ_hour"))
    )

    occ_features = (
        occ_with_capacity
        .groupBy("room_id")
        .agg(
            # avg_occ_ratio = avg(occupancy) / room_capacity, clamped to [0, 1].
            # capacity=0 rooms yield null (no meaningful ratio).
            F.when(
                F.first("capacity") > 0,
                F.least(F.mean("avg") / F.first("capacity"), F.lit(1.0)),
            ).alias("avg_occ_ratio"),
            F.count("_time").alias("occ_hours"),
        )
        .join(peak_hour, on="room_id", how="left")
    )

    # Data completeness: how many hourly windows had any sensor data?
    all_hours = sdf.groupBy("room_id").agg(
        F.countDistinct("_time").alias("observed_hours")
    )

    # Final join
    features = (
        rooms.select("room_id", "building_id", "room_type")
        .join(temp_features,   on="room_id", how="left")
        .join(energy_features, on="room_id", how="left")
        .join(occ_features,    on="room_id", how="left")
        .join(all_hours,       on="room_id", how="left")
        .withColumn("data_completeness",
                    F.col("observed_hours") / F.lit(EXPECTED_HOURS))
        .withColumn("week_start", F.to_date(F.lit(week_label)))
        .select(
            "week_start", "room_id", "building_id", "room_type",
            "avg_occ_ratio", "peak_occ_hour", "avg_temp_c",
            "total_energy_kwh", "data_completeness",
        )
    )

    write_ml_features(features)
    spark.stop()

    logger.info("Wrote ML feature rows", extra={"week": week_label})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    args = _parse_args()
    run(args.week_start)
