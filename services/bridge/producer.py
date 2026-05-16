"""
Async Kafka producer wrapper built on aiokafka.

Design choices:
- One shared AIOKafkaProducer instance per process (aiokafka is not thread-safe
  but is coroutine-safe within a single event loop).
- enable_idempotence=True ensures exactly-once delivery per producer session
  even if the broker retries due to network errors.
- lz4 compression gives ~4:1 ratio on JSON sensor payloads with negligible CPU.
"""

from __future__ import annotations

import json
import logging

from aiokafka import AIOKafkaProducer

from .config import config

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Lifecycle-managed async Kafka producer."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Create and start the aiokafka producer."""
        kwargs = dict(
            bootstrap_servers    = config.kafka_bootstrap_servers,
            enable_idempotence   = True,
            compression_type     = config.kafka_compression,
            max_batch_size       = config.kafka_batch_size,
            linger_ms            = config.kafka_linger_ms,
            acks                 = config.kafka_acks,
            value_serializer     = lambda v: json.dumps(v).encode() if isinstance(v, dict) else v,
            key_serializer       = lambda k: k if isinstance(k, bytes) else k.encode(),
            security_protocol    = config.kafka_security_protocol,
        )
        if config.kafka_security_protocol.upper() in ("SASL_PLAINTEXT", "SASL_SSL"):
            kwargs["sasl_mechanism"]     = config.kafka_sasl_mechanism
            kwargs["sasl_plain_username"] = config.kafka_sasl_username
            kwargs["sasl_plain_password"] = config.kafka_sasl_password
        self._producer = AIOKafkaProducer(**kwargs)
        await self._producer.start()
        logger.info("Kafka producer started", extra={"servers": config.kafka_bootstrap_servers})

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def send(self, topic: str, key: bytes, value: bytes) -> None:
        """
        Send one message.  Non-blocking: aiokafka batches internally.
        Re-raises KafkaConnectionError so the caller can decide to back off.
        """
        if self._producer is None:
            raise RuntimeError("Producer not started — call await producer.start() first")
        await self._producer.send(topic, key=key, value=value)

    async def send_dlq(self, raw: bytes, reason: str) -> None:
        """Route an unparseable or invalid payload to the dead-letter topic."""
        dlq_payload = json.dumps({"reason": reason, "raw": raw.decode(errors="replace")}).encode()
        await self.send(config.kafka_dlq_topic, key=b"dlq", value=dlq_payload)
        logger.warning("Message routed to DLQ", extra={"reason": reason})
