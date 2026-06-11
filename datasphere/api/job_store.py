"""
Couche de persistance des jobs — SQLite avec fallback mémoire.

Usage:
    from datasphere.api.job_store import job_store
    job_store.create(job_id, status="pending")
    job_store.update(job_id, status="completed", result={...})
    job_store.get(job_id) -> dict | None
    job_store.list_all() -> list[dict]
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class _InMemoryStore:
    """Fallback store quand SQLite n'est pas disponible."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, status: str = "pending", meta: dict | None = None) -> None:
        with self._lock:
            self._data[job_id] = {
                "job_id":     job_id,
                "status":     status,
                "result":     None,
                "error":      "",
                "created_at": time.time(),
                "updated_at": time.time(),
                "meta":       meta or {},
            }

    def update(
        self, job_id: str, status: str,
        result: Any = None, error: str = ""
    ) -> None:
        with self._lock:
            if job_id in self._data:
                self._data[job_id].update({
                    "status":     status,
                    "result":     result,
                    "error":      error,
                    "updated_at": time.time(),
                })

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return dict(self._data[job_id]) if job_id in self._data else None

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {"job_id": v["job_id"], "status": v["status"], "created_at": v["created_at"]}
                for v in sorted(self._data.values(), key=lambda x: x["created_at"], reverse=True)
            ]

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._data.pop(job_id, None)

    def purge_old(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        with self._lock:
            old = [jid for jid, v in self._data.items() if v["created_at"] < cutoff]
            for jid in old:
                del self._data[jid]
        return len(old)


class SQLiteJobStore:
    """Stockage persistant des jobs dans SQLite."""

    _DDL = """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id     TEXT PRIMARY KEY,
        status     TEXT NOT NULL,
        result     TEXT,
        error      TEXT DEFAULT '',
        meta       TEXT DEFAULT '{}',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
    """

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(self._DDL)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, job_id: str, status: str = "pending", meta: dict | None = None) -> None:
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO jobs (job_id, status, meta, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (job_id, status, json.dumps(meta or {}), now, now),
            )
            conn.commit()

    def update(
        self, job_id: str, status: str,
        result: Any = None, error: str = ""
    ) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, result=?, error=?, updated_at=? WHERE job_id=?",
                (status, json.dumps(result) if result is not None else None, error, time.time(), job_id),
            )
            conn.commit()

    def get(self, job_id: str) -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["result"] = json.loads(d["result"]) if d["result"] else None
            d["meta"]   = json.loads(d["meta"]) if d["meta"] else {}
            return d

    def list_all(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT job_id, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete(self, job_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
            conn.commit()

    def purge_old(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount


def _build_store():
    """
    Build the appropriate job store based on environment variables.

    Priority:
    1. DATASPHERE_REDIS_URL → RedisJobStore (multi-worker safe)
    2. DATASPHERE_JOB_DB   → SQLiteJobStore (single-worker, persisted)
    3. fallback             → _InMemoryStore (testing / no deps)
    """
    import logging
    _log = logging.getLogger(__name__)

    redis_url = os.environ.get("DATASPHERE_REDIS_URL", "")
    if redis_url:
        try:
            from datasphere.api.job_store_redis import RedisJobStore
            store = RedisJobStore(redis_url)
            _log.info("job_store_backend=redis url=%s", redis_url)
            return store
        except Exception as exc:
            _log.warning("redis_job_store_failed fallback=sqlite error=%s", exc)

    db_path = os.environ.get(
        "DATASPHERE_JOB_DB",
        str(Path.home() / ".datasphere" / "jobs.db"),
    )
    try:
        store = SQLiteJobStore(db_path)
        _log.info("job_store_backend=sqlite path=%s", db_path)
        return store
    except Exception as exc:
        _log.warning("sqlite_job_store_failed fallback=memory error=%s", exc)
        return _InMemoryStore()


job_store = _build_store()
