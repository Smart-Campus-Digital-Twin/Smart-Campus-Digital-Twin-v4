"""
Bridge service entry point — MQTT → Kafka.

Architecture:
  1. Subscribe to `campus/#` on Mosquitto with QoS 1.
  2. For each message: validate with Pydantic → wrap in KafkaMessage → send to Kafka.
  3. Invalid messages (bad JSON, schema violations) → sensors.dlq topic.
  4. Metrics exposed on :9090/metrics.

The entire service is a single asyncio event loop.  MQTT callbacks are
synchronous (paho requirement) but immediately schedule coroutines on the loop
via loop.call_soon_threadsafe, so the Kafka producer is always driven from the
same thread and the aiokafka internal buffer stays consistent.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from shared.logging_config import get_logger

from .config import config
from .metrics import metrics, serve_metrics
from .producer import KafkaProducer
from .validator import MQTTPayloadValidator

logger = get_logger("bridge", config.log_level)

# ---------------------------------------------------------------------------
# Global state shared between MQTT callbacks and the async event loop
# ---------------------------------------------------------------------------
_producer   = KafkaProducer()
_validator  = MQTTPayloadValidator()
_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------------------
# MQTT callbacks (called from paho's network thread)
# ---------------------------------------------------------------------------

def _on_connect(client: mqtt.Client, userdata: None, flags: dict, rc: int, props=None) -> None:
    if rc == 0:
        logger.info("Connected to MQTT broker", extra={"host": config.mqtt_host, "port": config.mqtt_port})
        client.subscribe(config.mqtt_topic_sub, qos=1)
        logger.info(f"Subscribed to {config.mqtt_topic_sub}")
    else:
        logger.error(f"MQTT connection failed, rc={rc}")


def _on_disconnect(client: mqtt.Client, userdata: None, flags: dict, rc: int, props=None) -> None:
    logger.warning("Disconnected from MQTT broker", extra={"rc": rc})


def _on_message(client: mqtt.Client, userdata: None, msg: mqtt.MQTTMessage) -> None:
    """
    Called on paho's network thread.  Hands work off to the event loop so that
    the async Kafka producer is always used from the same thread.
    """
    if _loop is None:
        raise RuntimeError("_on_message called before event loop was initialised")
    _loop.call_soon_threadsafe(
        asyncio.ensure_future,
        _handle_message(msg.topic, bytes(msg.payload)),
    )


# ---------------------------------------------------------------------------
# Async message handler (runs on the event loop)
# ---------------------------------------------------------------------------

async def _handle_message(topic: str, raw: bytes) -> None:
    try:
        message = _validator.parse(topic, raw)
    except ValueError as exc:
        # Malformed JSON — route to DLQ but don't crash.
        logger.warning("Malformed JSON", extra={"topic": topic, "error": str(exc)})
        metrics.record("unknown", valid=False)
        try:
            await _producer.send_dlq(raw, reason=str(exc))
        except Exception as dlq_exc:
            metrics.dlq_errors += 1
            logger.error("DLQ write failed", extra={"error": str(dlq_exc)}, exc_info=True)
        return
    except ValidationError as exc:
        # Schema violation — route to DLQ.
        logger.warning(
            "Schema validation failed",
            extra={"topic": topic, "errors": exc.error_count()},
        )
        metrics.record("unknown", valid=False)
        try:
            await _producer.send_dlq(raw, reason=exc.json())
        except Exception as dlq_exc:
            metrics.dlq_errors += 1
            logger.error("DLQ write failed", extra={"error": str(dlq_exc)}, exc_info=True)
        return

    reading = message.reading
    payload = message.to_json().encode()

    try:
        await _producer.send(
            topic = reading.kafka_topic,
            key   = reading.kafka_key,
            value = payload,
        )
        metrics.record(str(reading.sensor_type), valid=True)
        logger.debug(
            "Forwarded reading",
            extra={
                "kafka_topic": reading.kafka_topic,
                "room_id":     reading.room_id,
                "sensor_type": reading.sensor_type,
            },
        )
    except Exception as exc:  # noqa: BLE001 — aiokafka raises various subclasses
        metrics.kafka_errors += 1
        logger.error(
            "Kafka send failed",
            extra={"error": str(exc), "topic": reading.kafka_topic},
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run() -> None:
    global _loop
    _loop = asyncio.get_running_loop()

    await _producer.start()
    asyncio.ensure_future(serve_metrics())

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="campus-bridge",
    )
    client.username_pw_set(config.mqtt_username, config.mqtt_password)
    client.on_connect    = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message    = _on_message

    client.connect_async(config.mqtt_host, config.mqtt_port, config.mqtt_keepalive)
    client.loop_start()

    logger.info("Bridge started")

    # Wait until cancelled (Ctrl-C or SIGTERM)
    stop = asyncio.Event()
    _loop.add_signal_handler(signal.SIGTERM, stop.set)
    _loop.add_signal_handler(signal.SIGINT,  stop.set)
    await stop.wait()

    logger.info("Shutting down bridge...")
    client.loop_stop()
    client.disconnect()
    await _producer.stop()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
