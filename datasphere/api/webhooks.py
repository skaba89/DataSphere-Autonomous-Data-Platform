"""
Webhook registry and delivery engine for DataSphere API.

Webhooks are fired when a job transitions to completed/failed.
Delivery is retried with exponential backoff (up to 5 attempts).
"""
from __future__ import annotations
import json
import logging
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
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


class WebhookRegistry:
    """In-memory webhook registry with thread-safe delivery."""

    def __init__(self):
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._deliveries: list[WebhookDelivery] = []
        self._lock = threading.Lock()

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
            self._webhooks[wh.id] = wh
        return wh

    def unregister(self, webhook_id: str, tenant_id: str) -> bool:
        """Remove a webhook. Returns True if found and removed."""
        with self._lock:
            wh = self._webhooks.get(webhook_id)
            if wh and wh.tenant_id == tenant_id:
                del self._webhooks[webhook_id]
                return True
        return False

    def list_for_tenant(self, tenant_id: str) -> list[WebhookRegistration]:
        with self._lock:
            return [w for w in self._webhooks.values() if w.tenant_id == tenant_id and w.active]

    def get(self, webhook_id: str) -> WebhookRegistration | None:
        return self._webhooks.get(webhook_id)

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

    def recent_deliveries(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """Return recent delivery records for a tenant."""
        with self._lock:
            tenant_wh_ids = {w.id for w in self._webhooks.values() if w.tenant_id == tenant_id}
            relevant = [d for d in self._deliveries if d.webhook_id in tenant_wh_ids]
            relevant.sort(key=lambda d: d.delivered_at or 0, reverse=True)
            return [vars(d) for d in relevant[:limit]]


# Module-level singleton
webhook_registry = WebhookRegistry()
