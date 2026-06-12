"""Tests for API versioning — /v1/ prefix and deprecation headers on unversioned routes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from datasphere.api.app import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# v1 versioned routes
# ---------------------------------------------------------------------------

def test_v1_generate_sync_works(client):
    resp = client.post(
        "/v1/generate/sync",
        json={
            "business_request": "Test pipeline",
            "mode": "explicit",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
        },
    )
    assert resp.status_code == 200


def test_v1_dbt_generate_works(client):
    resp = client.post(
        "/v1/dbt/generate",
        json={"business_request": "Analytics pipeline"},
    )
    assert resp.status_code == 200


def test_v1_terraform_generate_works(client):
    resp = client.post(
        "/v1/terraform/generate",
        json={"business_request": "Cloud infra", "cloud_provider": "aws"},
    )
    assert resp.status_code == 200


def test_v1_jobs_list_works(client):
    resp = client.get("/v1/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_v1_health_works(client):
    resp = client.get("/v1/healthz")
    assert resp.status_code == 200


def test_v1_readyz_works(client):
    resp = client.get("/v1/readyz")
    assert resp.status_code in (200, 503)  # 503 if deps unavailable in test env


def test_v1_metrics_works(client):
    resp = client.get("/v1/metrics")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Deprecation headers
# ---------------------------------------------------------------------------

def test_unversioned_has_deprecation_header(client):
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.headers.get("deprecation") == "true"
    assert "/v1/jobs" in resp.headers.get("link", "")


def test_v1_no_deprecation_header(client):
    resp = client.get("/v1/jobs")
    assert resp.status_code == 200
    assert "deprecation" not in resp.headers


def test_x_api_version_header_on_all_responses(client):
    """X-API-Version must be present on all responses."""
    for path in ["/v1/jobs", "/jobs", "/healthz", "/"]:
        resp = client.get(path)
        assert resp.headers.get("x-api-version") == "1", (
            f"Missing X-API-Version on {path}"
        )


# ---------------------------------------------------------------------------
# Root documents api_versions
# ---------------------------------------------------------------------------

def test_root_lists_api_versions(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_versions" in body
    assert body["api_versions"]["current"] == "v1"
    assert "/v1" in body["api_versions"]["v1"]


# ---------------------------------------------------------------------------
# SDK client uses /v1/ prefix
# ---------------------------------------------------------------------------

def test_sdk_client_uses_v1_prefix(client):
    """DataSphereClient with default api_version='v1' routes requests to /v1/ paths."""
    from datasphere.client import DataSphereClient

    # Patch _post/_get to record the URL they call
    called_urls: list[str] = []

    class _TrackingClient(DataSphereClient):
        def _post(self, path, payload):
            import json
            called_urls.append(path)
            # Delegate to test client
            resp = client.post(
                f"{self._version_prefix}{path}",
                json=payload,
            )
            if resp.status_code >= 400:
                from datasphere.client import DataSphereError
                raise DataSphereError(f"POST {path} → {resp.status_code}")
            return resp.json()

        def _get(self, path):
            called_urls.append(path)
            resp = client.get(f"{self._version_prefix}{path}")
            if resp.status_code >= 400:
                from datasphere.client import DataSphereError
                raise DataSphereError(f"GET {path} → {resp.status_code}")
            return resp.json()

    sdk = _TrackingClient("http://testserver", api_version="v1")
    assert sdk._version_prefix == "/v1"

    # Confirm list_jobs hits /v1/jobs
    sdk.list_jobs()
    assert called_urls[-1] == "/jobs"  # path before prefix
    assert sdk._version_prefix == "/v1"
