"""Cache abstraction with two interchangeable backends.

Redis is used when reachable; otherwise the service degrades to a process-local
cache. That keeps a standalone `docker run` working while still exercising a
shared cache under docker compose.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Cache(ABC):
    """Minimal key/value cache holding JSON-serialisable values."""

    #: Human readable name, surfaced by the health endpoint.
    backend: str

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class InMemoryTTLCache(Cache):
    """Fallback backend: a dictionary with per-entry expiry."""

    backend = "in-memory"

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._entries.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._entries[key] = (time.monotonic() + ttl_seconds, value)

    async def close(self) -> None:
        self._entries.clear()


class RedisCache(Cache):
    """Shared backend, used when a Redis instance answers PING."""

    backend = "redis"

    def __init__(self, client: Any) -> None:
        self._client = client

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("valor não desserializável no cache, chave=%s", key)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)

    async def close(self) -> None:
        await self._client.aclose()


async def build_cache(redis_url: str | None) -> Cache:
    """Return a Redis-backed cache when possible, an in-process one otherwise."""
    if not redis_url:
        logger.info("REDIS_URL não configurada, usando cache em memória")
        return InMemoryTTLCache()

    try:
        import redis.asyncio as redis_asyncio

        client = redis_asyncio.from_url(redis_url, decode_responses=True)
        await client.ping()
    except Exception as exc:  # noqa: BLE001 - qualquer falha deve degradar, não derrubar
        logger.warning("Redis indisponível (%s), usando cache em memória", exc)
        return InMemoryTTLCache()

    logger.info("cache Redis conectado em %s", redis_url)
    return RedisCache(client)
