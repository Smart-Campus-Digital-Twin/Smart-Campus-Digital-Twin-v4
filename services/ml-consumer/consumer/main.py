"""
ML Consumer — Kafka → InfluxDB + Postgres anomaly store.

Replaces Flink stream processing. Reads sensor data from Kafka topics,
writes time-series to InfluxDB, runs anomaly detection rules, persists
anomaly events to Postgres, and optionally loads ML models from MLflow.

Architecture:
  - One AIOKafka consumer per topic group
  - Async write pipeline: parse → validate → influx_write + anomaly_check
  - Anomalies persisted to Postgres anomaly_events table
  - Prometheus metrics on :9091/metrics
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from .anomaly import AnomalyDetector
from .influx_writer import InfluxWriter
from .metrics import ConsumerMetrics, serve_metrics
from .pg_writer import PgWriter

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ml-consumer")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPICS = [
    os.getenv("KAFKA_TOPIC_TEMPERATURE", "sensors.temperature"),
    os.getenv("KAFKA_TOPIC_OCCUPANCY", "sensors.occupancy"),
    os.getenv("KAFKA_TOPIC_ENERGY", "sensors.energy"),
]
GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "campus-ml-consumer")


async def process_message(
    topic: str,
    payload: dict,
    influx: InfluxWriter,
    pg: PgWriter,
    detector: AnomalyDetector,
    metrics: ConsumerMetrics,
) -> None:
    """Parse one Kafka message and dispatch to InfluxDB + anomaly checker."""
    try:
        # Write to InfluxDB
        await influx.write(topic, payload)
        metrics.record_processed(topic)

        # Run anomaly detection
        anomalies = detector.check(topic, payload)
        for anomaly in anomalies:
            await pg.write_anomaly(anomaly)
            metrics.record_anomaly(topic)
            logger.warning(
                "Anomaly detected",
                extra={
                    "topic": topic,
                    "room_id": payload.get("room_id"),
                    "rule": anomaly["rule"],
                    "value": anomaly["value"],
                },
            )
    except Exception as exc:  # noqa: BLE001
        metrics.record_error(topic)
        logger.error(
            "Message processing failed",
            extra={"topic": topic, "error": str(exc)},
            exc_info=True,
        )


async def consume_loop(
    influx: InfluxWriter,
    pg: PgWriter,
    detector: AnomalyDetector,
    metrics: ConsumerMetrics,
    stop_event: asyncio.Event,
) -> None:
    """Main Kafka consume loop — runs until stop_event is set."""
    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda b: b,  # raw bytes — we parse below
    )

    # Retry connect until Kafka is up
    while not stop_event.is_set():
        try:
            await consumer.start()
            logger.info(
                "Kafka consumer started",
                extra={"topics": TOPICS, "group": GROUP_ID},
            )
            break
        except KafkaConnectionError as exc:
            logger.warning(f"Kafka not ready, retrying in 5s: {exc}")
            await asyncio.sleep(5)

    try:
        logger.info("Starting message consumption loop")
        async for msg in consumer:
            if stop_event.is_set():
                break
            logger.info(f"Received message from {msg.topic}, partition {msg.partition}, offset {msg.offset}")
            try:
                payload = json.loads(msg.value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                metrics.record_error(msg.topic)
                logger.warning(f"Bad message on {msg.topic}: {exc}")
                continue

            await process_message(
                msg.topic, payload, influx, pg, detector, metrics
            )
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped.")


async def run() -> None:
    """Entry point — wires all components and runs until SIGTERM/SIGINT."""
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    influx = InfluxWriter()
    pg = PgWriter()
    detector = AnomalyDetector()
    metrics = ConsumerMetrics()

    await pg.init()

    # Serve Prometheus metrics on :9091
    asyncio.ensure_future(serve_metrics(port=9091))

    logger.info("ML Consumer starting up", extra={"topics": TOPICS})

    await consume_loop(influx, pg, detector, metrics, stop_event)

    await influx.close()
    await pg.close()
    logger.info("ML Consumer shut down cleanly.")


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
