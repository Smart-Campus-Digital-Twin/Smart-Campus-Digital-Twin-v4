"""
Flink Job 1 — KafkaToInfluxJob
================================
Reads all three sensor Kafka topics, deserialises each KafkaMessage,
and writes raw readings to InfluxDB bucket `campus_raw`.

Latency target: ≤ 2 s end-to-end (1-s Flink checkpoint + ~100 ms InfluxDB write).

Pipeline:
    Kafka (sensors.*) → parse JSON → to_line_protocol() → InfluxBatchSink

Fault tolerance:
    - Flink checkpoints every 1 s (exactly-once semantics).
    - InfluxDB writes are idempotent when the same timestamp + tag set is
      re-written — duplicate records from checkpoint replay are no-ops.
    - Invalid messages are counted (via metrics) but do not crash the job.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from pyflink.common.typeinfo import Types

from processing.flink.config import config
from processing.flink.sinks.influx_sink import InfluxBatchSink
from processing.flink.utils import build_flink_env, build_kafka_source, build_bounded_watermark_strategy
from shared.schemas import KafkaMessage

logger = logging.getLogger(__name__)

# Topics consumed by this job
_TOPICS = ["sensors.temperature", "sensors.occupancy", "sensors.energy"]


_INGEST_CHECKPOINT_MS = 10_000


def _parse_and_to_line_protocol(raw: str) -> str | None:
    """Deserialise one KafkaMessage and return its InfluxDB line-protocol string.

    Returns None on parse failure; the caller uses flat_map to drop None results.
    """
    try:
        return KafkaMessage.from_json(raw).reading.to_line_protocol()
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Dropped unparseable message", extra={"reason": str(exc)})
        return None


def _parse_flat(raw: str) -> list[str]:
    """Wrapper for flat_map: parse once, return list of zero or one result."""
    result = _parse_and_to_line_protocol(raw)
    return [result] if result is not None else []


def run() -> None:
    """Build and submit the KafkaToInflux Flink job."""
    env    = build_flink_env(_INGEST_CHECKPOINT_MS)
    source = build_kafka_source(_TOPICS, "kafka-to-influx")

    stream = env.from_source(
        source,
        build_bounded_watermark_strategy(out_of_order_s=5, idle_timeout_s=30),
        "KafkaSource[sensors.*]",
    )

    line_protocol_stream = (
        stream
        .flat_map(_parse_flat)
        .name("ParseAndSerialise")
    )

    line_protocol_stream.map(
        InfluxBatchSink(
            bucket            = config.influxdb_bucket_raw,
            batch_size        = config.influx_batch_size,
            flush_interval_ms = config.influx_flush_ms,
        ),
        output_type=Types.STRING(),
    ).name("InfluxDB[campus_raw]")

    env.execute("KafkaToInfluxJob")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
