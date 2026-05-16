"""Shared PostgreSQL connection factory used by all services."""

from __future__ import annotations

from urllib.parse import urlparse

import psycopg2
import psycopg2.extensions

_CONNECT_TIMEOUT_S = 5


def get_db_connection(database_url: str) -> psycopg2.extensions.connection:
    """Return a new psycopg2 connection parsed from a postgresql:// DSN.

    Raises ValueError for a malformed DSN missing the database name.
    Raises psycopg2.OperationalError on connection failure (never swallowed).
    """
    parsed = urlparse(database_url)
    dbname = parsed.path.lstrip("/") if parsed.path else ""
    if not dbname:
        raise ValueError(
            f"DATABASE_URL is missing the database name: {database_url!r}. "
            "Expected format: postgresql://user:pass@host:port/dbname"
        )
    return psycopg2.connect(
        host            = parsed.hostname,
        port            = parsed.port or 5432,
        dbname          = dbname,
        user            = parsed.username,
        password        = parsed.password,
        connect_timeout = _CONNECT_TIMEOUT_S,
    )
