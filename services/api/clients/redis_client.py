"""
Redis client for distributed caching.

Caches frequently accessed data like:
- /campus/zones (5s TTL)
- Building aggregations (10s TTL)
- Room latest data (5s TTL)
"""

from __future__ import annotations

import json
import os
from typing import Any

import redis.asyncio as redis

from shared.logging_config import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Async Redis client for caching API responses."""

    def __init__(self) -> None:
        self._client: redis.Redis | None = None
        self._url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._client = await redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            await self._client.ping()
            logger.info(f"Connected to Redis at {self._url}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self._client = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Any | None:
        """Get cached value. Returns None if not found or Redis unavailable."""
        if not self._client:
            return None
        try:
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Redis GET error for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 60) -> bool:
        """Set cached value with TTL. Returns True if successful."""
        if not self._client:
            return False
        try:
            serialized = json.dumps(value)
            await self._client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis SET error for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete cached value. Returns True if successful."""
        if not self._client:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE error for key '{key}': {e}")
            return False

    async def ping(self) -> bool:
        """Check if Redis is available."""
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False
