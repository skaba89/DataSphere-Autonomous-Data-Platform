"""
Webhook registry and delivery engine for DataSphere API.

Webhooks are fired when a job transitions to completed/failed.
Delivery is retried with exponential backoff (up to 5 attempts).

Storage backends (selected at module load time):
  - Redis  — if DATASPHERE_REDIS_URL is set
  - SQLite — default, stored alongside jobs.db
  - Memory — fallback if both above fail
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_RETRY_DELAYS = [2, 4, 8, 16, 32]  # seconds between attempts
_TIMEOUT = 10  # seconds per attempt


@dataclass
class WebhookRegistration:
    id: str
    url: str
    tenant_id: str
    events: list[str]  # ["job.completed", "job.failed", "*"]
    secret: str = ""   # HMAC-SHA256 signing secret (optional)
    created_at: float = field(default_factory=time.time)
    active: bool = True


@dataclass
class WebhookDelivery:
    webhook_id: str
    job_id: str
    event: str
    attempts: int
    last_status_code: int | None
    success: bool
    delivered_at: float | None


# ---------------------------------------------------------------------------
# Persistent store backends
# ---------------------------------------------------------------------------

class _SQLiteWebhookStore:
    """SQLite-backed webhook storage."""

    _DDL = """
    CREATE TABLE IF NOT EXISTS webhooks (
        id         TEXT PRIMARY KEY,
        url        TEXT NOT NULL,
        tenant_id  TEXT NOT NULL,
        events     TEXT NOT NULL,
        secret     TEXT DEFAULT '',
        active     INTEGER DEFAULT 1,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_webhooks_tenant ON webhooks(tenant_id);

    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id     TEXT NOT NULL,
        job_id         TEXT NOT NULL,
        event          TEXT NOT NULL,
        attempts       INTEGER DEFAULT 0,
        last_status    INTEGER,
        success        INTEGER DEFAULT 0,
        delivered_at   REAL,
        created_at     REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_deliveries_webhook ON webhook_deliveries(webhook_id);
    """

    def __init__(self, db_path: str):
        import sqlite3
        self._path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(self._DDL)

    def _conn(self):
        import sqlite3
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def save_webhook(self, wh: WebhookRegistration) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO webhooks
                        (id, url, tenant_id, events, secret, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        wh.id,
                        wh.url,
                        wh.tenant_id,
                        json.dumps(wh.events),
                        wh.secret,
                        1 if wh.active else 0,
                        wh.created_at,
                    ),
                )

    def delete_webhook(self, webhook_id: str) -> bool:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    "DELETE FROM webhooks WHERE id = ?", (webhook_id,)
                )
                return cur.rowcount > 0

    def list_webhooks(self, tenant_id: str) -> list[WebhookRegistration]:
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM webhooks WHERE tenant_id = ? AND active = 1",
                    (tenant_id,),
                ).fetchall()
        result = []
        for row in rows:
            result.append(
                WebhookRegistration(
                    id=row["id"],
                    url=row["url"],
                    tenant_id=row["tenant_id"],
                    events=json.loads(row["events"]),
                    secret=row["secret"] or "",
                    active=bool(row["active"]),
                    created_at=row["created_at"],
                )
            )
        return result

    def save_delivery(self, delivery: WebhookDelivery) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO webhook_deliveries
                        (webhook_id, job_id, event, attempts, last_status,
                         success, delivered_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        delivery.webhook_id,
                        delivery.job_id,
                        delivery.event,
                        delivery.attempts,
                        delivery.last_status_code,
                        1 if delivery.success else 0,
                        delivery.delivered_at,
                        time.time(),
                    ),
                )

    def recent_deliveries(self, tenant_ids: set[str], limit: int = 50) -> list[dict]:
        if not tenant_ids:
            return []
        placeholders = ",".join("?" * len(tenant_ids))
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    f"""
                    SELECT d.webhook_id, d.job_id, d.event, d.attempts,
                           d.last_status AS last_status_code,
                           d.success, d.delivered_at
                    FROM webhook_deliveries d
                    JOIN webhooks w ON w.id = d.webhook_id
                    WHERE w.tenant_id IN ({placeholders})
                    ORDER BY d.delivered_at DESC
                    LIMIT ?
                    """,
                    (*tenant_ids, limit),
                ).fetchall()
        return [
            {
                "webhook_id": r["webhook_id"],
                "job_id": r["job_id"],
                "event": r["event"],
                "attempts": r["attempts"],
                "last_status_code": r["last_status_code"],
                "success": bool(r["success"]),
                "delivered_at": r["delivered_at"],
            }
            for r in rows
        ]


class _RedisWebhookStore:
    """Redis-backed webhook storage.

    Keys:
      datasphere:webhook:{id}             — JSON blob
      datasphere:webhooks:tenant:{tid}    — sorted set (score=created_at)
      datasphere:webhook_deliveries:{tid} — list (LPUSH + LTRIM to 100)
    """

    def __init__(self, redis_url: str):
        import redis as _redis
        self._r = _redis.from_url(redis_url, decode_responses=True)
        self._r.ping()  # fail fast if unreachable

    def _wh_key(self, wh_id: str) -> str:
        return f"datasphere:webhook:{wh_id}"

    def _tenant_key(self, tenant_id: str) -> str:
        return f"datasphere:webhooks:tenant:{tenant_id}"

    def _delivery_key(self, tenant_id: str) -> str:
        return f"datasphere:webhook_deliveries:{tenant_id}"

    def save_webhook(self, wh: WebhookRegistration) -> None:
        blob = json.dumps(
            {
                "id": wh.id,
                "url": wh.url,
                "tenant_id": wh.tenant_id,
                "events": wh.events,
                "secret": wh.secret,
                "active": wh.active,
                "created_at": wh.created_at,
            }
        )
        pipe = self._r.pipeline()
        pipe.set(self._wh_key(wh.id), blob)
        pipe.zadd(self._tenant_key(wh.tenant_id), {wh.id: wh.created_at})
        pipe.execute()

    def delete_webhook(self, webhook_id: str) -> bool:
        blob = self._r.get(self._wh_key(webhook_id))
        if blob is None:
            return False
        data = json.loads(blob)
        pipe = self._r.pipeline()
        pipe.delete(self._wh_key(webhook_id))
        pipe.zrem(self._tenant_key(data["tenant_id"]), webhook_id)
        pipe.execute()
        return True

    def list_webhooks(self, tenant_id: str) -> list[WebhookRegistration]:
        ids = self._r.zrange(self._tenant_key(tenant_id), 0, -1)
        result = []
        for wh_id in ids:
            blob = self._r.get(self._wh_key(wh_id))
            if blob is None:
                continue
            d = json.loads(blob)
            if not d.get("active", True):
                continue
            result.append(
                WebhookRegistration(
                    id=d["id"],
                    url=d["url"],
                    tenant_id=d["tenant_id"],
                    events=d["events"],
                    secret=d.get("secret", ""),
                    active=d.get("active", True),
                    created_at=d["created_at"],
                )
            )
        return result

    def save_delivery(self, delivery: WebhookDelivery) -> None:
        # Look up tenant_id from webhook blob
        blob = self._r.get(self._wh_key(delivery.webhook_id))
        if blob is None:
            return
        tenant_id = json.loads(blob).get("tenant_id", "unknown")
        record = json.dumps(
            {
                "webhook_id": delivery.webhook_id,
                "job_id": delivery.job_id,
                "event": delivery.event,
                "attempts": delivery.attempts,
                "last_status_code": delivery.last_status_code,
                "success": delivery.success,
                "delivered_at": delivery.delivered_at,
            }
        )
        pipe = self._r.pipeline()
        pipe.lpush(self._delivery_key(tenant_id), record)
        pipe.ltrim(self._delivery_key(tenant_id), 0, 99)
        pipe.execute()

    def recent_deliveries(self, tenant_ids: set[str], limit: int = 50) -> list[dict]:
        result = []
        for tid in tenant_ids:
            raw = self._r.lrange(self._delivery_key(tid), 0, limit - 1)
            for item in raw:
                result.append(json.loads(item))
        result.sort(key=lambda d: d.get("delivered_at") or 0, reverse=True)
        return result[:limit]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class WebhookRegistry:
    """Thread-safe webhook registry with optional persistent backend."""

    def __init__(self, store=None):
        self._store = store  # _SQLiteWebhookStore | _RedisWebhookStore | None
        self._memory: dict[str, WebhookRegistration] = {}
        self._deliveries: list[WebhookDelivery] = []  # in-memory delivery log
        self._lock = threading.Lock()

    def _load_from_store(self, tenant_id: str) -> None:
        """Lazy-load from persistent store into the memory cache."""
        if not self._store:
            return
        try:
            for wh in self._store.list_webhooks(tenant_id):
                if wh.id not in self._memory:
                    self._memory[wh.id] = wh
        except Exception as exc:
            _log.warning("webhook_store_load_failed error=%s", exc)

    def register(self, url, tenant_id, events=None, secret="") -> WebhookRegistration:
        """Register a new webhook. Returns the registration."""
        import uuid
        wh = WebhookRegistration(
            id=str(uuid.uuid4()),
            url=url,
            tenant_id=tenant_id,
            events=events or ["*"],
            secret=secret,
        )
        with self._lock:
            self._memory[wh.id] = wh
        if self._store:
            try:
                self._store.save_webhook(wh)
            except Exception as exc:
                _log.warning("webhook_store_save_failed error=%s", exc)
        return wh

    def unregister(self, webhook_id: str, tenant_id: str) -> bool:
        """Remove a webhook. Returns True if found and removed."""
        removed = False
        with self._lock:
            wh = self._memory.get(webhook_id)
            if wh and wh.tenant_id == tenant_id:
                del self._memory[webhook_id]
                removed = True
        if not removed and self._store:
            # May have been persisted but not yet in memory cache
            try:
                for wh in self._store.list_webhooks(tenant_id):
                    if wh.id == webhook_id:
                        removed = self._store.delete_webhook(webhook_id)
                        return removed
            except Exception as exc:
                _log.warning("webhook_store_unregister_failed error=%s", exc)
        if removed and self._store:
            try:
                self._store.delete_webhook(webhook_id)
            except Exception as exc:
                _log.warning("webhook_store_delete_failed error=%s", exc)
        return removed

    def list_for_tenant(self, tenant_id: str) -> list[WebhookRegistration]:
        self._load_from_store(tenant_id)
        with self._lock:
            return [w for w in self._memory.values() if w.tenant_id == tenant_id and w.active]

    def get(self, webhook_id: str) -> WebhookRegistration | None:
        return self._memory.get(webhook_id)

    def fire(self, event: str, job_id: str, tenant_id: str, payload: dict) -> None:
        """Fire webhook asynchronously in a background thread."""
        webhooks = [
            w for w in self.list_for_tenant(tenant_id)
            if "*" in w.events or event in w.events
        ]
        for wh in webhooks:
            t = threading.Thread(
                target=self._deliver,
                args=(wh, event, job_id, payload),
                daemon=True,
            )
            t.start()

    def _deliver(self, wh: WebhookRegistration, event: str, job_id: str, payload: dict) -> None:
        """Attempt delivery with exponential backoff."""
        body = json.dumps({
            "event": event,
            "job_id": job_id,
            "tenant_id": wh.tenant_id,
            "timestamp": time.time(),
            "data": payload,
        }).encode()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DataSphere-Webhook/1.2",
            "X-DataSphere-Event": event,
            "X-DataSphere-Job-ID": job_id,
        }

        if wh.secret:
            import hmac
            import hashlib
            sig = hmac.new(wh.secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-DataSphere-Signature"] = f"sha256={sig}"

        delivery = WebhookDelivery(
            webhook_id=wh.id,
            job_id=job_id,
            event=event,
            attempts=0,
            last_status_code=None,
            success=False,
            delivered_at=None,
        )

        for i, delay in enumerate([0] + _RETRY_DELAYS):
            if delay > 0:
                time.sleep(delay)
            try:
                req = urllib.request.Request(wh.url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    delivery.attempts += 1
                    delivery.last_status_code = resp.status
                    if 200 <= resp.status < 300:
                        delivery.success = True
                        delivery.delivered_at = time.time()
                        _log.info(
                            "webhook_delivered wh=%s event=%s job=%s attempt=%d",
                            wh.id[:8], event, job_id[:8], delivery.attempts,
                        )
                        break
            except urllib.error.HTTPError as exc:
                delivery.attempts += 1
                delivery.last_status_code = exc.code
                _log.warning(
                    "webhook_http_error wh=%s status=%d attempt=%d",
                    wh.id[:8], exc.code, delivery.attempts,
                )
            except Exception as exc:
                delivery.attempts += 1
                _log.warning(
                    "webhook_delivery_failed wh=%s error=%s attempt=%d",
                    wh.id[:8], exc, delivery.attempts,
                )

        with self._lock:
            self._deliveries.append(delivery)

        if self._store:
            try:
                self._store.save_delivery(delivery)
            except Exception as exc:
                _log.warning("webhook_store_delivery_save_failed error=%s", exc)

    def recent_deliveries(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """Return recent delivery records for a tenant."""
        if self._store:
            try:
                with self._lock:
                    tenant_wh_ids = {
                        w.id for w in self._memory.values() if w.tenant_id == tenant_id
                    }
                # Also include IDs not yet in memory cache
                self._load_from_store(tenant_id)
                with self._lock:
                    tenant_wh_ids = {
                        w.id for w in self._memory.values() if w.tenant_id == tenant_id
                    }
                return self._store.recent_deliveries(tenant_wh_ids, limit=limit)
            except Exception as exc:
                _log.warning("webhook_store_deliveries_failed fallback=memory error=%s", exc)

        with self._lock:
            tenant_wh_ids = {w.id for w in self._memory.values() if w.tenant_id == tenant_id}
            relevant = [d for d in self._deliveries if d.webhook_id in tenant_wh_ids]
            relevant.sort(key=lambda d: d.delivered_at or 0, reverse=True)
            return [vars(d) for d in relevant[:limit]]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_webhook_registry() -> WebhookRegistry:
    redis_url = os.environ.get("DATASPHERE_REDIS_URL", "")
    if redis_url:
        try:
            store = _RedisWebhookStore(redis_url)
            _log.info("webhook_store=redis")
            return WebhookRegistry(store=store)
        except Exception as exc:
            _log.warning("redis_webhook_store_failed fallback=sqlite error=%s", exc)

    db_path = os.environ.get(
        "DATASPHERE_JOB_DB", str(Path.home() / ".datasphere" / "jobs.db")
    )
    webhooks_db = db_path.replace("jobs.db", "webhooks.db")
    try:
        store = _SQLiteWebhookStore(webhooks_db)
        _log.info("webhook_store=sqlite path=%s", webhooks_db)
        return WebhookRegistry(store=store)
    except Exception as exc:
        _log.warning("sqlite_webhook_store_failed fallback=memory error=%s", exc)
        return WebhookRegistry()


# Module-level singleton
webhook_registry = _build_webhook_registry()
