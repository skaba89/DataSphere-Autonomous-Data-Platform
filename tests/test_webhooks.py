"""Tests for the webhook registry and delivery engine."""
from __future__ import annotations
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry():
    """Return a fresh WebhookRegistry instance for isolation."""
    from datasphere.api.webhooks import WebhookRegistry
    return WebhookRegistry()


def _mock_urlopen_200():
    """Return a context-manager mock that simulates HTTP 200."""
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    cm = MagicMock(return_value=resp)
    return cm


# ---------------------------------------------------------------------------
# Unit tests — WebhookRegistry
# ---------------------------------------------------------------------------

def test_register_webhook_returns_id():
    reg = _make_registry()
    wh = reg.register("https://example.com/hook", "tenant1")
    assert wh.id
    assert wh.url == "https://example.com/hook"
    assert wh.tenant_id == "tenant1"


def test_list_webhooks_empty_initially():
    reg = _make_registry()
    assert reg.list_for_tenant("tenant1") == []


def test_register_and_list_webhook():
    reg = _make_registry()
    reg.register("https://example.com/hook", "tenant1", ["job.completed"])
    webhooks = reg.list_for_tenant("tenant1")
    assert len(webhooks) == 1
    assert webhooks[0].url == "https://example.com/hook"
    assert webhooks[0].events == ["job.completed"]


def test_delete_webhook():
    reg = _make_registry()
    wh = reg.register("https://example.com/hook", "tenant1")
    removed = reg.unregister(wh.id, "tenant1")
    assert removed is True
    assert reg.list_for_tenant("tenant1") == []


def test_delete_nonexistent_webhook_returns_false():
    reg = _make_registry()
    result = reg.unregister("nonexistent-id", "tenant1")
    assert result is False


def test_fire_calls_url():
    reg = _make_registry()
    reg.register("https://example.com/hook", "tenant1", ["*"])
    mock_open = _mock_urlopen_200()

    with patch("urllib.request.urlopen", mock_open):
        reg.fire("job.completed", "job-123", "tenant1", {"success": True})
        # Give the background thread time to run
        time.sleep(0.2)

    assert mock_open.called


def test_fire_only_matching_events():
    """Register for job.completed only; fire job.failed — should not call URL."""
    reg = _make_registry()
    reg.register("https://example.com/hook", "tenant1", ["job.completed"])
    mock_open = _mock_urlopen_200()

    with patch("urllib.request.urlopen", mock_open):
        reg.fire("job.failed", "job-456", "tenant1", {"error": "boom"})
        time.sleep(0.2)

    assert not mock_open.called


def test_fire_wildcard_matches_all_events():
    reg = _make_registry()
    reg.register("https://example.com/hook", "tenant1", ["*"])
    mock_open = _mock_urlopen_200()

    with patch("urllib.request.urlopen", mock_open):
        reg.fire("job.failed", "job-789", "tenant1", {"error": "oops"})
        time.sleep(0.2)

    assert mock_open.called


def test_webhook_registry_tenant_isolation():
    reg = _make_registry()
    reg.register("https://tenanta.com/hook", "tenantA")
    reg.register("https://tenantb.com/hook", "tenantB")

    a_hooks = reg.list_for_tenant("tenantA")
    b_hooks = reg.list_for_tenant("tenantB")

    assert len(a_hooks) == 1
    assert a_hooks[0].url == "https://tenanta.com/hook"
    assert len(b_hooks) == 1
    assert b_hooks[0].url == "https://tenantb.com/hook"


def test_hmac_signature_in_headers():
    """When a secret is set the X-DataSphere-Signature header must be present."""
    reg = _make_registry()
    reg.register("https://example.com/hook", "tenant1", ["*"], secret="mysecret")

    captured_headers: dict = {}

    def fake_urlopen(req, timeout=None):
        captured_headers.update(req.headers)
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        reg.fire("job.completed", "job-hmac", "tenant1", {})
        time.sleep(0.2)

    # Header keys are title-cased by urllib
    sig_header = captured_headers.get("X-datasphere-signature") or captured_headers.get("X-DataSphere-Signature")
    assert sig_header is not None
    assert sig_header.startswith("sha256=")


def test_delivery_recorded_after_success():
    reg = _make_registry()
    wh = reg.register("https://example.com/hook", "tenant1", ["*"])
    mock_open = _mock_urlopen_200()

    with patch("urllib.request.urlopen", mock_open):
        reg.fire("job.completed", "job-rec", "tenant1", {"success": True})
        time.sleep(0.3)

    deliveries = reg.recent_deliveries("tenant1")
    assert len(deliveries) >= 1
    assert deliveries[0]["success"] is True
    assert deliveries[0]["webhook_id"] == wh.id


# ---------------------------------------------------------------------------
# API endpoint tests — TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_registry(monkeypatch):
    """Swap the module-level webhook_registry singleton with a fresh one."""
    from datasphere.api import webhooks
    from datasphere.api.webhooks import WebhookRegistry
    new_reg = WebhookRegistry()
    monkeypatch.setattr(webhooks, "webhook_registry", new_reg)
    # Also patch the reference imported into app.py
    import datasphere.api.app as app_mod
    monkeypatch.setattr(app_mod, "webhook_registry", new_reg)
    return new_reg


@pytest.fixture
def api_client(fresh_registry):
    from datasphere.api.app import app
    return TestClient(app)


def test_api_register_endpoint(api_client):
    resp = api_client.post("/webhooks", json={"url": "https://example.com/hook", "events": ["*"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["url"] == "https://example.com/hook"
    assert data["events"] == ["*"]


def test_api_list_endpoint(api_client):
    api_client.post("/webhooks", json={"url": "https://example.com/hook1"})
    api_client.post("/webhooks", json={"url": "https://example.com/hook2"})
    resp = api_client.get("/webhooks")
    assert resp.status_code == 200
    hooks = resp.json()
    assert len(hooks) == 2


def test_api_delete_endpoint(api_client):
    reg_resp = api_client.post("/webhooks", json={"url": "https://example.com/hook"})
    wh_id = reg_resp.json()["id"]
    del_resp = api_client.delete(f"/webhooks/{wh_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == wh_id
    # Verify it's gone
    list_resp = api_client.get("/webhooks")
    assert list_resp.json() == []


def test_delete_nonexistent_webhook_404(api_client):
    resp = api_client.delete("/webhooks/nonexistent-id")
    assert resp.status_code == 404


def test_api_deliveries_endpoint(api_client, fresh_registry):
    # Register and manually inject a delivery record
    wh = fresh_registry.register("https://example.com/hook", "default")
    from datasphere.api.webhooks import WebhookDelivery
    fresh_registry._deliveries.append(WebhookDelivery(
        webhook_id=wh.id,
        job_id="job-001",
        event="job.completed",
        attempts=1,
        last_status_code=200,
        success=True,
        delivered_at=time.time(),
    ))
    resp = api_client.get("/webhooks/deliveries")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["success"] is True
    assert items[0]["event"] == "job.completed"


# ---------------------------------------------------------------------------
# Persistence tests — _SQLiteWebhookStore and WebhookRegistry with store
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_store(tmp_path):
    """Return a fresh _SQLiteWebhookStore backed by a temp file."""
    from datasphere.api.webhooks import _SQLiteWebhookStore
    return _SQLiteWebhookStore(str(tmp_path / "webhooks.db"))


def test_sqlite_store_save_and_list(sqlite_store):
    from datasphere.api.webhooks import WebhookRegistration
    wh = WebhookRegistration(
        id="wh-001",
        url="https://example.com/hook",
        tenant_id="tenant1",
        events=["job.completed"],
        secret="s3cr3t",
        created_at=time.time(),
        active=True,
    )
    sqlite_store.save_webhook(wh)
    result = sqlite_store.list_webhooks("tenant1")
    assert len(result) == 1
    assert result[0].id == "wh-001"
    assert result[0].url == "https://example.com/hook"
    assert result[0].events == ["job.completed"]
    assert result[0].secret == "s3cr3t"


def test_sqlite_store_delete(sqlite_store):
    from datasphere.api.webhooks import WebhookRegistration
    wh = WebhookRegistration(
        id="wh-002",
        url="https://example.com/hook",
        tenant_id="tenant1",
        events=["*"],
        created_at=time.time(),
    )
    sqlite_store.save_webhook(wh)
    assert len(sqlite_store.list_webhooks("tenant1")) == 1
    deleted = sqlite_store.delete_webhook("wh-002")
    assert deleted is True
    assert sqlite_store.list_webhooks("tenant1") == []
    # Deleting again returns False
    assert sqlite_store.delete_webhook("wh-002") is False


def test_sqlite_store_delivery_saved(sqlite_store):
    from datasphere.api.webhooks import WebhookRegistration, WebhookDelivery
    wh = WebhookRegistration(
        id="wh-003",
        url="https://example.com/hook",
        tenant_id="tenantX",
        events=["*"],
        created_at=time.time(),
    )
    sqlite_store.save_webhook(wh)
    delivery = WebhookDelivery(
        webhook_id="wh-003",
        job_id="job-abc",
        event="job.completed",
        attempts=1,
        last_status_code=200,
        success=True,
        delivered_at=time.time(),
    )
    sqlite_store.save_delivery(delivery)
    rows = sqlite_store.recent_deliveries({"tenantX"}, limit=10)
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["event"] == "job.completed"
    assert rows[0]["job_id"] == "job-abc"


def test_registry_with_sqlite_store_persists(tmp_path):
    """Webhook registered via registry should be readable from the store directly."""
    from datasphere.api.webhooks import _SQLiteWebhookStore, WebhookRegistry
    db = str(tmp_path / "wh.db")
    store = _SQLiteWebhookStore(db)
    reg = WebhookRegistry(store=store)
    wh = reg.register("https://persist.example.com/hook", "tenantP", ["job.failed"])
    # Read back directly from the store (bypass registry memory)
    from_store = store.list_webhooks("tenantP")
    assert len(from_store) == 1
    assert from_store[0].id == wh.id
    assert from_store[0].url == "https://persist.example.com/hook"


def test_registry_loads_from_store_on_list(tmp_path):
    """Webhooks inserted directly into the store appear when listing via a new registry."""
    from datasphere.api.webhooks import _SQLiteWebhookStore, WebhookRegistry, WebhookRegistration
    db = str(tmp_path / "wh2.db")
    store = _SQLiteWebhookStore(db)
    # Insert directly into the store, bypassing any registry
    wh = WebhookRegistration(
        id="wh-direct",
        url="https://direct.example.com/hook",
        tenant_id="tenantD",
        events=["*"],
        created_at=time.time(),
    )
    store.save_webhook(wh)
    # A brand-new registry backed by the same store should see it
    reg = WebhookRegistry(store=store)
    webhooks = reg.list_for_tenant("tenantD")
    assert len(webhooks) == 1
    assert webhooks[0].id == "wh-direct"
    assert webhooks[0].url == "https://direct.example.com/hook"
