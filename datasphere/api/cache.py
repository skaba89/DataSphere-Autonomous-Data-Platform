"""Simple TTL cache: Redis when available, else in-process dict."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

_MISSING = object()


class _InProcessCache:
    """Thread-safe in-process TTL cache backed by a plain dict."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        """Return cached value or _MISSING if absent/expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return _MISSING
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return _MISSING
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store *value* under *key* for *ttl* seconds."""
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        """Remove *key* from the cache (no-op if absent)."""
        with self._lock:
            self._store.pop(key, None)


class _RedisCache:
    """TTL cache backed by Redis (serialises values as JSON)."""

    def __init__(self, redis_url: str) -> None:
        import redis  # type: ignore[import]

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        # Verify connectivity immediately so _build_cache() can fall back on failure.
        self._client.ping()

    def get(self, key: str) -> Any:
        """Return cached value or _MISSING if absent/expired."""
        raw = self._client.get(key)
        if raw is None:
            return _MISSING
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return _MISSING

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store *value* under *key* for *ttl* seconds."""
        self._client.setex(key, ttl, json.dumps(value))

    def delete(self, key: str) -> None:
        """Remove *key* from the cache."""
        self._client.delete(key)


def _build_cache() -> _InProcessCache | _RedisCache:
    import os

    url = os.getenv("DATASPHERE_REDIS_URL")
    if url:
        try:
            return _RedisCache(url)
        except Exception:
            pass
    return _InProcessCache()


# Module-level singleton — import this everywhere.
cache = _build_cache()
MISSING = _MISSING
