"""
Spark Job — DailyEnergyReportJob
==================================
Reads the previous day's hourly aggregations from InfluxDB `campus_1h`
and writes per-building daily energy totals to PostgreSQL `energy_daily`.

Triggered at 00:30 daily (after all 24 hourly roll-ups are complete).

Energy calculation:
    total_kwh = SUM(sum_avg_W * 3600 s/h) / 1000 W/kW  [per building per day]
    peak_w    = MAX(max_W)                               [peak instantaneous demand]
    avg_w     = MEAN(avg_W)                              [average demand]

sample_hours: count of hourly windows that had data. < 24 flags a partial day
(sensor outage or late Flink checkpoint), so downstream consumers can weight
this day appropriately in ML training.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
from influxdb_client import InfluxDBClient
from pyspark.sql import functions as F

from processing.spark.config import config
from processing.spark.utils import build_spark_session
from processing.spark.utils.postgres_writer import write_energy_daily

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily energy report job")
    p.add_argument("--date", type=str, default=None,
                   help="Date to process YYYY-MM-DD. Defaults to yesterday.")
    return p.parse_args()


def _day_window(date_str: str | None) -> tuple[datetime, datetime]:
    if date_str:
        start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=1)
    return start, start + timedelta(days=1)


def run(date_str: str | None = None) -> None:
    start, stop = _day_window(date_str)
    date_label  = start.strftime("%Y-%m-%d")
    logger.info(f"Building energy report for {date_label}")

    # ---------------------------------------------------------------------------
    # Read hourly energy aggregations for the target day from InfluxDB
    # ---------------------------------------------------------------------------
    start_rfc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc  = stop.strftime("%Y-%m-%dT%H:%M:%SZ")

    flux = f"""
from(bucket: "{config.influxdb_bucket_1h}")
  |> range(start: {start_rfc}, stop: {stop_rfc})
  |> filter(fn: (r) => r._measurement =~ /^sensor_1h_/)
  |> filter(fn: (r) => r.sensor_type == "energy")
  |> pivot(
       rowKey: ["_time", "building_id", "room_id"],
       columnKey: ["_field"],
       valueColumn: "_value"
     )
  |> keep(columns: ["_time", "building_id", "avg", "max", "sum_avg"])
"""

    client = InfluxDBClient(url=config.influxdb_url, token=config.influxdb_token, org=config.influxdb_org)
    try:
        pdf = client.query_api().query_data_frame(flux)
    finally:
        client.close()

    if isinstance(pdf, list):
        pdf = pd.concat(pdf, ignore_index=True) if pdf else pd.DataFrame()
    if pdf is None or pdf.empty:
        logger.warning(f"No energy data for {date_label} — skipping")
        return

    spark = build_spark_session("DailyEnergyReport")
    spark.sparkContext.setLogLevel("WARN")

    sdf = spark.createDataFrame(pdf)

    daily = (
        sdf
        .groupBy("building_id")
        .agg(
            (F.sum("sum_avg") * 3600 / 1000).alias("total_kwh"),
            F.max("max").alias("peak_w"),
            F.mean("avg").alias("avg_w"),
            F.countDistinct("_time").alias("sample_hours"),
        )
        .withColumn("date", F.to_date(F.lit(date_label)))
    )

    write_energy_daily(daily)
    spark.stop()

    logger.info("Wrote building energy rows", extra={"date": date_label})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    args = _parse_args()
    run(args.date)
