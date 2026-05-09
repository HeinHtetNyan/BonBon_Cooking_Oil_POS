"""
Redis connection management.

Two separate Redis pools are maintained:
- `redis_client`: general app use (pub/sub, rate limiting, flags)
- `redis_cache`: caching layer (separate DB index to allow targeted flush)

Both are initialized at app startup and closed at shutdown.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import settings
from app.core.exceptions import CacheError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisManager:
    def __init__(self) -> None:
        self._client: Redis | None = None
        self._cache: Redis | None = None

    def init(self) -> None:
        self._client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        self._cache = aioredis.from_url(
            settings.redis_cache_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        logger.info("redis.clients_initialized")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
        if self._cache:
            await self._cache.aclose()
        self._client = None
        self._cache = None
        logger.info("redis.clients_closed")

    async def ping(self) -> bool:
        try:
            if self._client:
                return bool(await self._client.ping())
            return False
        except RedisConnectionError:
            return False

    @property
    def client(self) -> Redis:
        if not self._client:
            raise CacheError("Redis client is not initialized")
        return self._client

    @property
    def cache(self) -> Redis:
        if not self._cache:
            raise CacheError("Redis cache is not initialized")
        return self._cache


redis_manager = RedisManager()


async def get_redis() -> Redis:
    """FastAPI dependency for the general Redis client."""
    return redis_manager.client


async def get_redis_cache() -> Redis:
    """FastAPI dependency for the caching Redis client."""
    return redis_manager.cache
