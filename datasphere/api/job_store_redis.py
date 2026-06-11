"""
Redis-backed job store for DataSphere API.

Drop-in replacement for SQLiteJobStore when running multiple workers.
Activated automatically when DATASPHERE_REDIS_URL is set.

Usage:
    DATASPHERE_REDIS_URL=redis://localhost:6379/0 uvicorn datasphere.api.app:app --workers 4
"""
from __future__ import annotations
import json
import os
import time
import threading
from typing import Any

_REDIS_TTL = 86400 * 7  # 7 days


class RedisJobStore:
    """
    Job store backed by Redis.
    Compatible interface with SQLiteJobStore / _InMemoryStore.
    """

    def __init__(self, url: str):
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "redis package is required: pip install redis"
            ) from exc
        self._client = redis.from_url(url, decode_responses=True)
        self._client.ping()  # fail fast if unreachable
        self._prefix = "datasphere:job:"

    def _key(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"

    def _index_key(self) -> str:
        return "datasphere:jobs:index"

    def create(self, job_id: str, status: str = "pending", meta: dict | None = None) -> None:
        record = {
            "job_id":     job_id,
            "status":     status,
            "result":     None,
            "error":      "",
            "meta":       json.dumps(meta or {}),
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        pipe = self._client.pipeline()
        pipe.set(self._key(job_id), json.dumps(record), ex=_REDIS_TTL)
        pipe.zadd(self._index_key(), {job_id: time.time()})
        pipe.expire(self._index_key(), _REDIS_TTL)
        pipe.execute()

    def update(self, job_id: str, status: str,
               result: dict | None = None, error: str = "") -> None:
        raw = self._client.get(self._key(job_id))
        if raw is None:
            return
        record = json.loads(raw)
        record["status"]     = status
        record["updated_at"] = time.time()
        if result is not None:
            record["result"] = result
        if error:
            record["error"] = error
        self._client.set(self._key(job_id), json.dumps(record), ex=_REDIS_TTL)

    def get(self, job_id: str) -> dict | None:
        raw = self._client.get(self._key(job_id))
        if raw is None:
            return None
        record = json.loads(raw)
        # Deserialize nested JSON fields
        if isinstance(record.get("meta"), str):
            try:
                record["meta"] = json.loads(record["meta"])
            except (json.JSONDecodeError, TypeError):
                record["meta"] = {}
        return record

    def list_all(self) -> list[dict]:
        # Get most recent 200 job IDs from sorted set
        job_ids = self._client.zrevrange(self._index_key(), 0, 199)
        results = []
        for job_id in job_ids:
            rec = self.get(job_id)
            if rec:
                results.append(rec)
        return results

    def delete(self, job_id: str) -> None:
        pipe = self._client.pipeline()
        pipe.delete(self._key(job_id))
        pipe.zrem(self._index_key(), job_id)
        pipe.execute()

    def purge_old(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        old_ids = self._client.zrangebyscore(self._index_key(), "-inf", cutoff)
        if not old_ids:
            return 0
        pipe = self._client.pipeline()
        for job_id in old_ids:
            pipe.delete(self._key(job_id))
        pipe.zremrangebyscore(self._index_key(), "-inf", cutoff)
        pipe.execute()
        return len(old_ids)
