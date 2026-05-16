"""
Root conftest.py — sets environment variables required by config validators
before any test module is imported.

Config classes in bridge/, processing/flink/, and api/ use pydantic-settings
with @model_validator that raise ValueError when secrets are empty strings.
Setting dummy values here prevents import-time failures in unit tests that
do not exercise the actual database or broker connections.
"""

import os

# MQTT credentials (bridge/config.py)
os.environ.setdefault("MQTT_USERNAME", "test-user")
os.environ.setdefault("MQTT_PASSWORD", "test-password")

# InfluxDB token (flink/config.py, api/config.py)
os.environ.setdefault("INFLUXDB_TOKEN", "test-influxdb-token-32-chars-long!")

# PostgreSQL DSN (flink/config.py, api/config.py, spark/config.py)
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/campus_test")
