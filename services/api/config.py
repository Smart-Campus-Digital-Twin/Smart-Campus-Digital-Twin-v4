"""FastAPI service configuration."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWN_BAD_SECRETS = frozenset({"changeme-admin-token", ""})


class APIConfig(BaseSettings):
    """API configuration; raises ValueError at startup on missing or insecure secrets."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # InfluxDB
    influxdb_url:        str = "http://influxdb:8086"
    influxdb_token:      str = ""
    influxdb_org:        str = "smart-campus"
    influxdb_bucket_raw: str = "campus_raw"
    influxdb_bucket_1m:  str = "campus_1m"
    influxdb_bucket_1h:  str = "campus_1h"

    # PostgreSQL
    database_url: str = ""

    # API
    api_title:    str       = "Smart Campus Digital Twin API"
    api_version:  str       = "1.0.0"
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level:    str       = "INFO"

    # Pagination defaults
    default_page_size: int = Field(100, ge=1, le=1000)

    @model_validator(mode="after")
    def _require_secrets(self) -> APIConfig:
        """Fail fast if any mandatory secret is missing or uses a known-bad default."""
        if self.influxdb_token in _KNOWN_BAD_SECRETS:
            raise ValueError(
                "INFLUXDB_TOKEN must be set (env var INFLUXDB_TOKEN)"
            )
        if self.database_url in _KNOWN_BAD_SECRETS:
            raise ValueError("DATABASE_URL must be set (env var DATABASE_URL)")
        return self


config = APIConfig()
settings = config  # alias used by some routers
