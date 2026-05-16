"""
Spark → PostgreSQL writer.

Uses the JDBC connector which ships with Spark.  The JDBC URL is built from
the config DATABASE_URL so no separate configuration is needed.

All writes use mode="append" with conflict handling done at the SQL level
(ON CONFLICT DO UPDATE) via a pre-write truncate strategy for idempotent runs.
For tables with natural primary keys (energy_daily, ml_features) we use
ON CONFLICT DO UPDATE to handle Airflow re-runs cleanly.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pyspark.sql import DataFrame

from processing.spark.config import config
from shared.db import get_db_connection

_JDBC_DRIVER = "org.postgresql.Driver"

_parsed = urlparse(config.database_url)
# Build JDBC URL without embedded credentials — pass user/password via properties instead,
# because the PostgreSQL JDBC driver misparses "user:pass@host" as the hostname when both
# URL credentials and property credentials are supplied simultaneously.
_JDBC_URL = (
    f"jdbc:postgresql://{_parsed.hostname}:{_parsed.port or 5432}{_parsed.path}"
)
_JDBC_PROPS: dict = {
    "user":     _parsed.username or "",
    "password": _parsed.password or "",
    "driver":   _JDBC_DRIVER,
}


def _jdbc_props() -> dict:
    """Return JDBC connection properties for Spark JDBC writes."""
    return _JDBC_PROPS


def write_energy_daily(df: DataFrame) -> None:
    """
    Write daily energy summary to PostgreSQL.

    Uses JDBC upsert via a temp table + INSERT ... ON CONFLICT.
    Spark JDBC doesn't natively support upsert so we write to a staging
    table and then merge in PostgreSQL.
    """
    props = _jdbc_props()
    df.write.jdbc(
        url        = _JDBC_URL,
        table      = "energy_daily_staging",
        mode       = "overwrite",   # recreate staging on each run
        properties = {**props, "truncate": "true"},
    )
    # Merge staging → target (idempotent upsert)
    _run_sql("""
        INSERT INTO energy_daily (date, building_id, total_kwh, peak_w, avg_w, sample_hours)
        SELECT date, building_id, total_kwh, peak_w, avg_w, sample_hours
        FROM energy_daily_staging
        ON CONFLICT (date, building_id)
        DO UPDATE SET
            total_kwh    = EXCLUDED.total_kwh,
            peak_w       = EXCLUDED.peak_w,
            avg_w        = EXCLUDED.avg_w,
            sample_hours = EXCLUDED.sample_hours,
            written_at   = now()
    """)


def write_ml_features(df: DataFrame) -> None:
    """Write weekly ML feature vectors to PostgreSQL."""
    props = _jdbc_props()
    df.write.jdbc(
        url        = _JDBC_URL,
        table      = "ml_features_staging",
        mode       = "overwrite",
        properties = {**props, "truncate": "true"},
    )
    _run_sql("""
        INSERT INTO ml_features (
            week_start, room_id, building_id, room_type,
            avg_occ_ratio, peak_occ_hour, avg_temp_c, total_energy_kwh, data_completeness
        )
        SELECT
            week_start, room_id, building_id, room_type,
            avg_occ_ratio, peak_occ_hour, avg_temp_c, total_energy_kwh, data_completeness
        FROM ml_features_staging
        ON CONFLICT (week_start, room_id)
        DO UPDATE SET
            avg_occ_ratio     = EXCLUDED.avg_occ_ratio,
            peak_occ_hour     = EXCLUDED.peak_occ_hour,
            avg_temp_c        = EXCLUDED.avg_temp_c,
            total_energy_kwh  = EXCLUDED.total_energy_kwh,
            data_completeness = EXCLUDED.data_completeness,
            written_at        = now()
    """)


def _run_sql(sql: str) -> None:
    """Execute a raw SQL statement on the driver node using psycopg2."""
    conn = get_db_connection(config.database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
