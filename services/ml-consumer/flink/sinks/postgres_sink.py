"""
PostgreSQL write sink for PyFlink — MapFunction implementation.

PyFlink's add_sink() requires a Java-backed SinkFunction.  Pure Python
sinks must use map() instead, returning a dummy value so Flink can infer
the output type.  The write to PostgreSQL happens as a side-effect inside
map(), and the returned DataStream of dummy strings is never used downstream.

Use with explicit output type:
    stream.map(PostgresBatchSink(), output_type=Types.STRING())
"""

from __future__ import annotations

import logging
import time
from typing import Any

import psycopg2
import psycopg2.extras
from pyflink.datastream.functions import MapFunction, RuntimeContext

from processing.flink.config import config

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO anomalies (
    anomaly_id, detected_at, sensor_id, building_id, floor, room_id,
    sensor_type, anomaly_type, severity, value, threshold, message
) VALUES %s
ON CONFLICT (anomaly_id) DO NOTHING
"""


class PostgresBatchSink(MapFunction):
    """
    Buffered PostgreSQL sink for AnomalyEvent row-tuples.

    Returns "ok" as a dummy STRING from map() so Flink can infer the output
    type.  Caller must use:
        stream.map(PostgresBatchSink(), output_type=Types.STRING())
    The resulting DataStream[str] is not consumed downstream.
    """

    def __init__(self, batch_size: int = 50, flush_interval_ms: int = 2000) -> None:
        self._batch_size        = batch_size
        self._flush_interval_ms = flush_interval_ms
        self._conn              = None
        self._buffer: list[tuple] = []
        self._last_flush_ms: int = 0

    def open(self, runtime_context: RuntimeContext) -> None:
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self._conn = psycopg2.connect(config.database_url)
                self._conn.autocommit = False
                self._last_flush_ms = int(time.time() * 1000)
                logger.info("PostgreSQL anomaly sink opened")
                return
            except psycopg2.OperationalError as exc:
                if attempt < max_retries - 1:
                    logger.warning(
                        "PostgreSQL connection failed, retrying",
                        extra={"attempt": attempt + 1, "max": max_retries, "error": str(exc)},
                    )
                    time.sleep(2)
                else:
                    logger.error("PostgreSQL connection failed after max retries")
                    raise

    def map(self, record: Any) -> str:
        """Buffer the row and flush on batch size or interval; return dummy."""
        self._buffer.append(tuple(record))
        now_ms = int(time.time() * 1000)
        if len(self._buffer) >= self._batch_size or \
                (now_ms - self._last_flush_ms) >= self._flush_interval_ms:
            self._flush()
        return "ok"

    def close(self) -> None:
        if self._buffer:
            self._flush()
        if self._conn:
            self._conn.close()

    def _flush(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush_ms = int(time.time() * 1000)
        try:
            with self._conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, _UPSERT_SQL, batch)
            self._conn.commit()
            logger.info("Flushed anomalies to PostgreSQL", extra={"count": len(batch)})
        except Exception as exc:
            self._conn.rollback()
            logger.error("PostgreSQL flush failed", extra={"error": str(exc)})
            raise
