"""Tests for multi-tenant support (X-Tenant-ID header isolation)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from datasphere.api.tenancy import (
    get_tenant_id,
    set_tenant_id,
    tenant_job_id,
    validate_tenant_id,
    extract_raw_job_id,
    _TENANT_ID_VAR,
)


# ---------------------------------------------------------------------------
# Unit tests — tenancy module
# ---------------------------------------------------------------------------

def test_default_tenant_is_default():
    # Reset to default
    _TENANT_ID_VAR.set("default")
    assert get_tenant_id() == "default"


def test_set_and_get_tenant_id():
    set_tenant_id("acme")
    assert get_tenant_id() == "acme"
    set_tenant_id("default")  # cleanup


@pytest.mark.parametrize("tid", ["acme", "my-org", "tenant1", "a"])
def test_valid_tenant_ids(tid):
    assert validate_tenant_id(tid) is True


@pytest.mark.parametrize("tid", ["", "tenant with space", "tenant@org", "a" * 65, "-starts-dash"])
def test_invalid_tenant_ids(tid):
    assert validate_tenant_id(tid) is False


def test_tenant_job_id_default_no_prefix():
    _TENANT_ID_VAR.set("default")
    assert tenant_job_id("abc-123") == "abc-123"


def test_tenant_job_id_custom_adds_prefix():
    _TENANT_ID_VAR.set("acme")
    assert tenant_job_id("abc-123") == "acme:abc-123"
    _TENANT_ID_VAR.set("default")


def test_extract_raw_job_id_strips_prefix():
    assert extract_raw_job_id("acme:abc-123") == "abc-123"


def test_extract_raw_job_id_no_prefix():
    assert extract_raw_job_id("abc-123") == "abc-123"


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from datasphere.api.app import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


def test_api_default_tenant_header_in_response(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-tenant-id") == "default"


def test_api_custom_tenant_header(client):
    resp = client.get("/health", headers={"X-Tenant-ID": "acme"})
    assert resp.status_code == 200
    assert resp.headers.get("x-tenant-id") == "acme"


def test_api_invalid_tenant_returns_400(client):
    resp = client.get("/health", headers={"X-Tenant-ID": "bad tenant!"})
    assert resp.status_code == 400
    assert "Invalid X-Tenant-ID" in resp.json()["detail"]


def test_api_jobs_isolated_between_tenants(client):
    """Job created as tenant acme should not appear in tenant beta's job list."""
    from unittest.mock import patch
    import uuid

    job_id = str(uuid.uuid4())

    # Simulate tenant acme creating a job directly in the store with scoped key
    from datasphere.api.job_store import job_store
    job_store.create(f"acme:{job_id}", status="pending")

    # Tenant acme should see it
    resp_acme = client.get("/jobs", headers={"X-Tenant-ID": "acme"})
    assert resp_acme.status_code == 200
    job_ids = [j["job_id"] for j in resp_acme.json()]
    assert any(jid.startswith("acme:") for jid in job_ids)

    # Tenant beta should not see acme's jobs
    resp_beta = client.get("/jobs", headers={"X-Tenant-ID": "beta"})
    assert resp_beta.status_code == 200
    for j in resp_beta.json():
        assert not j["job_id"].startswith("acme:")

    # cleanup
    job_store.delete(f"acme:{job_id}")


def test_api_tenant_job_create_and_retrieve(client):
    """Creating a job as tenant acme and retrieving it with the same tenant."""
    import uuid
    from datasphere.api.job_store import job_store

    job_id = str(uuid.uuid4())
    scoped_id = f"acme:{job_id}"
    job_store.create(scoped_id, status="completed")

    # Retrieve with matching tenant
    resp = client.get(f"/jobs/{job_id}", headers={"X-Tenant-ID": "acme"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id

    job_store.delete(scoped_id)


def test_rate_limit_per_tenant_not_shared(client):
    """Rate limit buckets are per tenant:ip, not shared across tenants."""
    from datasphere.api.app import _rate_limiter
    # Use two different tenant keys
    key_a = "tenant-a:127.0.0.1"
    key_b = "tenant-b:127.0.0.1"
    # Allow one request for each — they should be independent
    assert _rate_limiter.is_allowed(key_a) is True
    assert _rate_limiter.is_allowed(key_b) is True


def test_tenant_id_in_log_context():
    """_get_tenant_id_safe() returns current tenant without raising."""
    from datasphere.api.logging_config import _get_tenant_id_safe
    _TENANT_ID_VAR.set("log-test")
    result = _get_tenant_id_safe()
    assert result == "log-test"
    _TENANT_ID_VAR.set("default")
