"""Spark job configuration — sourced from environment variables."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWN_BAD_SECRETS = frozenset({"changeme", "changeme-admin-token", ""})


class SparkConfig(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # InfluxDB — read source for all Spark jobs
    influxdb_url:    str = "http://influxdb:8086"
    influxdb_token:  str = ""
    influxdb_org:    str = "smart-campus"

    influxdb_bucket_1m: str = "campus_1m"
    influxdb_bucket_1h: str = "campus_1h"
    influxdb_bucket_1d: str = "campus_1d"

    # PostgreSQL — write target for report and feature jobs
    database_url: str = ""

    # Spark
    spark_master:      str = "spark://spark-master:7077"
    spark_app_name:    str = "SmartCampus"
    spark_executor_mem: str = "1g"

    @model_validator(mode="after")
    def _require_secrets(self) -> "SparkConfig":
        """Fail fast if any mandatory secret uses a known-bad placeholder."""
        if self.influxdb_token in _KNOWN_BAD_SECRETS:
            raise ValueError(
                "INFLUXDB_TOKEN must be set via environment variable — "
                "placeholder value detected"
            )
        if "changeme" in self.database_url:
            raise ValueError(
                "DATABASE_URL must be set via environment variable — "
                "placeholder password detected"
            )
        return self


config = SparkConfig()
