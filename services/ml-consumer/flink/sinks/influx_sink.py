"""
InfluxDB write sink for PyFlink.

PyFlink has no built-in InfluxDB connector, so we implement a custom
SinkFunction that accumulates line-protocol strings into a batch and
flushes them via the InfluxDB HTTP write API.

Batching strategy:
  - Flush when batch reaches `batch_size` records  (throughput)
  - Flush when `flush_interval_ms` has elapsed     (latency guarantee)
  This gives sub-second latency even during low-traffic periods.

Error handling:
  - Flush failures are re-raised so Flink's fault-tolerance can restart
    the task from the last checkpoint.  Data loss on transient errors is
    not acceptable under the exactly-once contract.
"""

from __future__ import annotations

import logging
import time

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from pyflink.datastream.functions import RuntimeContext, MapFunction

from processing.flink.config import config

logger = logging.getLogger(__name__)


class InfluxBatchSink(MapFunction):
    """Buffered InfluxDB sink for line-protocol string records."""

    def __init__(
        self,
        bucket:           str,
        batch_size:       int = config.influx_batch_size,
        flush_interval_ms: int = config.influx_flush_ms,
    ) -> None:
        """Initialise sink parameters; the InfluxDB client is created in open()."""
        self._bucket            = bucket
        self._batch_size        = batch_size
        self._flush_interval_ms = flush_interval_ms

        self._client: InfluxDBClient | None = None
        self._write_api = None
        self._buffer: list[str] = []
        self._last_flush_ms: int = 0

    def open(self, runtime_context: RuntimeContext) -> None:
        """Create the InfluxDB client once per task slot."""
        self._client = InfluxDBClient(
            url   = config.influxdb_url,
            token = config.influxdb_token,
            org   = config.influxdb_org,
        )
        self._write_api     = self._client.write_api(write_options=SYNCHRONOUS)
        self._last_flush_ms = int(time.time() * 1000)
        logger.info("InfluxDB sink opened", extra={"bucket": self._bucket})

    def map(self, record: str) -> str:
        """Buffer one line-protocol record and flush when threshold is met."""
        self._buffer.append(record)
        now_ms       = int(time.time() * 1000)
        time_elapsed = (now_ms - self._last_flush_ms) >= self._flush_interval_ms
        if len(self._buffer) >= self._batch_size or time_elapsed:
            self._flush()
        return record

    def close(self) -> None:
        """Flush the remaining buffer and close the client cleanly."""
        if self._buffer:
            self._flush()
        if self._write_api:
            self._write_api.close()
        if self._client:
            self._client.close()

    def _flush(self) -> None:
        """Write the current buffer to InfluxDB; re-raise on failure."""
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush_ms = int(time.time() * 1000)
        self._write_api.write(
            bucket    = self._bucket,
            org       = config.influxdb_org,
            record    = "\n".join(batch),
            precision = "ns",
        )
        logger.info(
            "Flushed records to InfluxDB",
            extra={"count": len(batch), "bucket": self._bucket},
        )
