"""
Bridge service configuration — all values sourced from environment variables.

pydantic-settings reads env vars automatically; no manual os.getenv() calls.
Use env/mosquitto.env and env/kafka.env when running locally.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWN_BAD_SECRETS = frozenset({"changeme", ""})


class BridgeConfig(BaseSettings):
    """MQTT-to-Kafka bridge configuration; raises ValueError on insecure defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # MQTT broker
    mqtt_host:      str = "mosquitto"
    mqtt_port:      int = 1883
    mqtt_username:  str = ""
    mqtt_password:  str = ""
    mqtt_keepalive: int = 60
    mqtt_topic_sub: str = "campus/#"

    # Kafka producer
    kafka_bootstrap_servers:  str   = "kafka:9092"
    kafka_dlq_topic:          str   = "sensors.dlq"
    kafka_batch_size:         int   = 16384
    kafka_linger_ms:          int   = 5
    kafka_compression:        str   = "lz4"
    kafka_acks:               str   = "all"
    kafka_security_protocol:  str   = "PLAINTEXT"
    kafka_sasl_mechanism:     str   = "PLAIN"
    kafka_sasl_username:      str   = ""
    kafka_sasl_password:      str   = ""

    # Operational
    log_level:          str   = "INFO"
    publish_interval_s: float = 5.0

    @field_validator("mqtt_username", "mqtt_password")
    @classmethod
    def _validate_mqtt_creds(cls, v: str) -> str:
        if v in _KNOWN_BAD_SECRETS:
            raise ValueError("MQTT_USERNAME and MQTT_PASSWORD must be set")
        return v

    @field_validator("kafka_sasl_username", "kafka_sasl_password")
    @classmethod
    def _validate_kafka_sasl(cls, v: str, info) -> str:
        if info.data.get("kafka_security_protocol", "").upper() in ("SASL_PLAINTEXT", "SASL_SSL") and (not v or v == "changeme"):
            raise ValueError("Kafka SASL credentials required when SASL security protocol is used")
        return v


config = BridgeConfig()
