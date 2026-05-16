"""
Flink Job 2 — WindowAggJob
===========================
1-minute tumbling window aggregation using Flink Table API (SQL).

The DataStream AggregateFunction + ProcessWindowFunction combination
requires pickling complex Python classes through the Beam runner, which
is unreliable in PyFlink 1.20 remote mode. Table API SQL is the stable
alternative — Flink compiles SQL windows to JVM bytecode, so no Python
serialisation is needed for the windowing logic itself.

Pipeline:
  Kafka (sensors.*) — JSON with nested `reading` object
    → Flink SQL TUMBLE(1 min, PROCTIME)
    → DataStream[Row]
    → AggInfluxSink (MapFunction) → InfluxDB campus_1m

Output measurement: sensor_1m
Tags:  building_id, floor, room_id, sensor_type
Fields: min, max, avg, stddev, count, quality_avg
"""

from __future__ import annotations

import logging
import time

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from pyflink.common.typeinfo import Types
from pyflink.datastream.functions import MapFunction, RuntimeContext
from pyflink.table import StreamTableEnvironment

from processing.flink.config import config
from processing.flink.utils import build_flink_env

logger = logging.getLogger(__name__)


class AggInfluxSink(MapFunction):
    """MapFunction sink: receives one aggregated Row, writes line protocol to InfluxDB."""

    def open(self, runtime_context: RuntimeContext) -> None:
        self._client = InfluxDBClient(
            url=config.influxdb_url,
            token=config.influxdb_token,
            org=config.influxdb_org,
        )
        self._write_api     = self._client.write_api(write_options=SYNCHRONOUS)
        self._buffer: list[str] = []
        self._last_flush_ms = int(time.time() * 1000)
        logger.info("AggInfluxSink opened", extra={"bucket": config.influxdb_bucket_1m})

    def map(self, row) -> str:
        """
        Row column order matches the SELECT in the SQL query:
          0: window_start  (datetime)
          1: building_id   (str)
          2: floor         (int)
          3: room_id       (str)
          4: sensor_type   (str)
          5: min_v         (float)
          6: max_v         (float)
          7: avg_v         (float)
          8: stddev_v      (float | None)
          9: cnt           (int)
         10: quality_avg   (float)
        """
        try:
            ts_ns       = int(row[0].timestamp() * 1_000_000_000)
            sensor_type = str(row[4])
            measurement = f"sensor_1m_{sensor_type}"
            tags = (
                f"building_id={row[1]},"
                f"floor={row[2]},"
                f"room_id={row[3]},"
                f"sensor_type={sensor_type}"
            )
            if sensor_type == "occupancy":
                fields = (
                    f"min={int(round(float(row[5])))}i,"
                    f"max={int(round(float(row[6])))}i,"
                    f"avg={int(round(float(row[7])))}i,"
                    f"stddev=0i,"
                    f"count={int(row[9])}i,"
                    f"quality_avg={float(row[10])}"
                )
            else:
                stddev = float(row[8]) if row[8] is not None else 0.0
                fields = (
                    f"min={float(row[5])},"
                    f"max={float(row[6])},"
                    f"avg={float(row[7])},"
                    f"stddev={stddev},"
                    f"count={int(row[9])}i,"
                    f"quality_avg={float(row[10])}"
                )
            self._buffer.append(f"{measurement},{tags} {fields} {ts_ns}")
        except Exception as exc:
            logger.warning("Skipping malformed aggregation row", extra={"error": str(exc)})
            return "error"

        now_ms = int(time.time() * 1000)
        if len(self._buffer) >= 200 or (now_ms - self._last_flush_ms) >= 2000:
            self._flush()
        return "ok"

    def close(self) -> None:
        if self._buffer:
            self._flush()
        if hasattr(self, "_write_api"):
            self._write_api.close()
        if hasattr(self, "_client"):
            self._client.close()

    def _flush(self) -> None:
        if not self._buffer:
            return
        batch               = self._buffer[:]
        self._buffer.clear()
        self._last_flush_ms = int(time.time() * 1000)
        self._write_api.write(
            bucket    = config.influxdb_bucket_1m,
            org       = config.influxdb_org,
            record    = "\n".join(batch),
            precision = "ns",
        )
        logger.info("Flushed 1m aggregations to InfluxDB", extra={"count": len(batch)})


def run() -> None:
    env   = build_flink_env(checkpoint_interval_ms=5000)
    t_env = StreamTableEnvironment.create(env)

    # ------------------------------------------------------------------
    # Source — Kafka topics with the KafkaMessage envelope.
    # The `reading` column is a nested ROW; SQL extracts sub-fields.
    # ------------------------------------------------------------------
    bs      = config.kafka_bootstrap_servers
    gid     = f"{config.kafka_group_id_prefix}-window-agg-sql"
    # ROW<> type must be written on a single line — Flink SQL parser rejects
    # angle-bracket types that span multiple lines.
    # `floor` and `value` are reserved SQL keywords. Backtick-quoting tells the
    # Flink SQL parser they are identifiers; the JSON format maps by the bare name.
    t_env.execute_sql(
        "CREATE TABLE kafka_sensor_stream ("
        "  reading ROW<building_id STRING, `floor` INT, room_id STRING, sensor_type STRING, `value` DOUBLE, quality DOUBLE>,"
        "  proc_time AS PROCTIME()"
        ") WITH ("
        "  'connector'                    = 'kafka',"
        f" 'topic'                        = 'sensors.temperature;sensors.occupancy;sensors.energy',"
        f" 'properties.bootstrap.servers' = '{bs}',"
        f" 'properties.group.id'          = '{gid}',"
        "  'scan.startup.mode'            = 'latest-offset',"
        "  'format'                       = 'json',"
        "  'json.ignore-parse-errors'     = 'true'"
        ")"
    )

    # ------------------------------------------------------------------
    # 1-minute PROCTIME tumbling window aggregation.
    # PROCTIME windows fire exactly once per window close — no retractions,
    # so to_data_stream() receives a clean append stream.
    # ------------------------------------------------------------------
    agg_table = t_env.sql_query(
        "SELECT"
        "  TUMBLE_START(proc_time, INTERVAL '1' MINUTE) AS window_start,"
        "  reading.building_id  AS building_id,"
        "  reading.`floor`      AS bldg_floor,"
        "  reading.room_id      AS room_id,"
        "  reading.sensor_type  AS sensor_type,"
        "  MIN(reading.`value`)    AS min_v,"
        "  MAX(reading.`value`)    AS max_v,"
        "  AVG(reading.`value`)    AS avg_v,"
        "  STDDEV_POP(CAST(reading.`value` AS DOUBLE)) AS stddev_v,"
        "  COUNT(reading.`value`)  AS cnt,"
        "  AVG(reading.quality)    AS quality_avg"
        " FROM kafka_sensor_stream"
        " WHERE reading.quality >= 0.5"
        " GROUP BY"
        "  TUMBLE(proc_time, INTERVAL '1' MINUTE),"
        "  reading.building_id, reading.`floor`, reading.room_id, reading.sensor_type"
    )

    # ------------------------------------------------------------------
    # Convert Table → DataStream[Row] → InfluxDB sink
    # ------------------------------------------------------------------
    agg_stream = t_env.to_data_stream(agg_table)
    agg_stream.map(AggInfluxSink(), output_type=Types.STRING()).name("InfluxDB[campus_1m]")

    env.execute("WindowAggJob")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
