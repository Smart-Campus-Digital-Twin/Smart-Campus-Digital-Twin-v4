"""
Spark Job — HourlyRollupJob
============================
Reads the previous hour's 1-minute aggregations from InfluxDB `campus_1m`
and computes 1-hour aggregations, writing the results back to InfluxDB `campus_1h`.

Triggered by Airflow hourly_rollup_dag at hh:05 so the hh:00 window is complete.

Why Spark instead of Flink for this?
  Hourly rollup is inherently batch: a fixed 60-window scan, a single aggregation,
  done.  Flink's continuous processing overhead is wasted.  Spark starts, runs
  in seconds, and exits cleanly.  Airflow handles scheduling.

Output measurement: `sensor_1h` in bucket `campus_1h`
Output fields: min, max, avg, stddev (of the hour), sum_avg (for energy kWh calc),
               total_count (total samples in the hour), quality_avg
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from pyspark.sql import functions as F

from processing.spark.config import config
from processing.spark.utils import InfluxReader, build_spark_session

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hourly roll-up job")
    p.add_argument(
        "--hour",
        type=str,
        default=None,
        help="ISO-8601 hour to process, e.g. 2025-05-03T10:00:00Z. Defaults to previous hour.",
    )
    return p.parse_args()


def _hour_window(hour_str: str | None) -> tuple[datetime, datetime]:
    if hour_str:
        start = datetime.fromisoformat(hour_str).replace(tzinfo=timezone.utc)
    else:
        now   = datetime.now(timezone.utc)
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return start, start + timedelta(hours=1)


def run(hour_str: str | None = None) -> None:
    start, stop = _hour_window(hour_str)
    logger.info(f"Rolling up {start.isoformat()} → {stop.isoformat()}")

    # ---------------------------------------------------------------------------
    # Read 1-minute aggregations for the target hour
    # ---------------------------------------------------------------------------
    reader = InfluxReader()
    pdf    = reader.read_1m_window(
        bucket      = config.influxdb_bucket_1m,
        start       = start,
        stop        = stop,
    )
    reader.close()

    if pdf.empty:
        logger.warning(f"No data found for hour {start.isoformat()} — skipping")
        return

    spark = build_spark_session("HourlyRollup")
    spark.sparkContext.setLogLevel("WARN")

    sdf = spark.createDataFrame(pdf)

    hourly = (
        sdf
        .filter(F.col("quality_avg") >= 0.5)
        .groupBy("building_id", "floor", "room_id", "sensor_type")
        .agg(
            F.min("min").alias("min"),
            F.max("max").alias("max"),
            F.mean("avg").alias("avg"),
            F.stddev_pop("avg").alias("stddev"),
            F.sum("avg").alias("sum_avg"),
            F.sum("count").alias("total_count"),
            F.mean("quality_avg").alias("quality_avg"),
        )
    )

    result_pdf: pd.DataFrame = hourly.toPandas()
    spark.stop()

    # ---------------------------------------------------------------------------
    # Write to InfluxDB campus_1h
    # ---------------------------------------------------------------------------
    ts_ns   = int(start.timestamp() * 1e9)
    lines   = []

    for _, row in result_pdf.iterrows():
        tags = (
            f"building_id={row['building_id']},"
            f"floor={int(row['floor'])},"
            f"room_id={row['room_id']},"
            f"sensor_type={row['sensor_type']}"
        )
        fields = (
            f"min={row['min']},"
            f"max={row['max']},"
            f"avg={row['avg']},"
            f"stddev={0.0 if (row['stddev'] is None or (isinstance(row['stddev'], float) and math.isnan(row['stddev']))) else row['stddev']},"
            f"sum_avg={row['sum_avg']},"
            f"total_count={int(row['total_count'])}i,"
            f"quality_avg={row['quality_avg']}"
        )
        lines.append(f"sensor_1h,{tags} {fields} {ts_ns}")

    client    = InfluxDBClient(url=config.influxdb_url, token=config.influxdb_token, org=config.influxdb_org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_api.write(bucket=config.influxdb_bucket_1h, org=config.influxdb_org,
                    record="\n".join(lines), precision="ns")
    write_api.close()
    client.close()

    logger.info(f"Wrote {len(lines)} hourly aggregations to campus_1h")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    args = _parse_args()
    run(args.hour)
