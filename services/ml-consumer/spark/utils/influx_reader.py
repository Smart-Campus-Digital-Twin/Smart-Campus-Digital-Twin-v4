"""
InfluxDB → Spark DataFrame reader.

Uses the InfluxDB Python client to run Flux queries and returns the results
as a pandas DataFrame, which is then parallelised into a Spark DataFrame.

This is the standard pattern for InfluxDB + Spark integration:
  InfluxDB client (driver) → pandas DF → spark.createDataFrame()

For very large datasets (>10M rows), consider the InfluxDB Parquet export
API instead, but at campus scale (200 msg/sec × 7 days = ~120M rows max in
raw, much less in aggregated buckets) this pattern is sufficient.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from influxdb_client import InfluxDBClient

from processing.spark.config import config


class InfluxReader:
    """Read InfluxDB data into a pandas DataFrame."""

    def __init__(self) -> None:
        self._client = InfluxDBClient(
            url   = config.influxdb_url,
            token = config.influxdb_token,
            org   = config.influxdb_org,
        )

    def close(self) -> None:
        self._client.close()

    def query(self, flux: str) -> pd.DataFrame:
        """Execute a Flux query and return results as a pandas DataFrame."""
        query_api = self._client.query_api()
        result    = query_api.query_data_frame(flux)
        if isinstance(result, list):
            result = pd.concat(result, ignore_index=True)
        return result

    def read_1m_window(
        self,
        *,
        bucket:      str,
        start:       datetime,
        stop:        datetime,
        sensor_type: str | None = None,
    ) -> pd.DataFrame:
        """
        Read 1-minute aggregations from a bucket for a given time window.

        Returns a DataFrame with columns:
            _time, building_id, floor, room_id, sensor_type,
            min, max, avg, stddev, count, quality_avg
        """
        start_rfc = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_rfc  = stop.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        type_filter = (
            f'|> filter(fn: (r) => r.sensor_type == "{sensor_type}")'
            if sensor_type else ""
        )

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start_rfc}, stop: {stop_rfc})
  |> filter(fn: (r) => r._measurement =~ /^sensor_1m_/)
  {type_filter}
  |> pivot(
       rowKey: ["_time", "building_id", "floor", "room_id", "sensor_type"],
       columnKey: ["_field"],
       valueColumn: "_value"
     )
  |> keep(columns: ["_time", "building_id", "floor", "room_id", "sensor_type",
                     "min", "max", "avg", "stddev", "count", "quality_avg"])
"""
        return self.query(flux)
