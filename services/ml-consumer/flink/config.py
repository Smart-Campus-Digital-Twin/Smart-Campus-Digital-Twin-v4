"""Flink job configuration sourced entirely from environment variables."""

from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWN_BAD_SECRETS = frozenset({"changeme", "changeme-admin-token", ""})


class FlinkConfig(BaseSettings):
    """All Flink job settings; raises ValueError at startup on insecure defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    kafka_bootstrap_servers:  str = "kafka:9092"
    kafka_group_id_prefix:    str = "flink-campus"
    kafka_security_protocol:  str = "PLAINTEXT"
    kafka_sasl_mechanism:     str = "PLAIN"
    kafka_sasl_username:      str = ""
    kafka_sasl_password:      str = ""

    influxdb_url:        str = "http://influxdb:8086"
    influxdb_token:      str = ""
    influxdb_org:        str = "smart-campus"
    influxdb_bucket_raw: str = "campus_raw"
    influxdb_bucket_1m:  str = "campus_1m"
    influx_batch_size:   int = 200
    influx_flush_ms:     int = 500

    database_url: str = ""

    flink_master: str = "flink-jobmanager:8081"
    checkpoint_interval_ms: int   = 1000
    parallelism:  int = 2

    temp_high_threshold:    float = 38.0
    temp_low_threshold:     float = 14.0
    energy_spike_factor:    float = 5.0
    occupancy_cap_fraction: float = 1.05

    @field_validator("influxdb_token", "database_url")
    @classmethod
    def _require_secrets(cls, v: str) -> str:
        """Fail fast if any mandatory secret is missing or uses a known-bad default."""
        if v in _KNOWN_BAD_SECRETS:
            raise ValueError(
                "Secret field must be set via environment variable — "
                "placeholder or empty value detected"
            )
        return v

    @model_validator(mode="after")
    def _check_sasl(self) -> "FlinkConfig":
        """Validate SASL credentials are present when a SASL protocol is selected."""
        if self.kafka_security_protocol.upper() in ("SASL_PLAINTEXT", "SASL_SSL"):
            if not self.kafka_sasl_username or not self.kafka_sasl_password:
                raise ValueError(
                    "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD are required "
                    "when KAFKA_SECURITY_PROTOCOL is SASL_PLAINTEXT or SASL_SSL"
                )
        return self


config = FlinkConfig()
