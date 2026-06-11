"""
Integration tests against a live DataSphere API server.

Set DATASPHERE_BASE_URL to run these tests, e.g.:
    DATASPHERE_BASE_URL=http://localhost:18000 pytest tests/test_docker_integration.py -v

All tests are skipped when DATASPHERE_BASE_URL is not set.
"""

import json
import os
import time
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("DATASPHERE_BASE_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="DATASPHERE_BASE_URL not set")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def _post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_healthz():
    """GET /healthz returns 200 + {"status": "ok"}."""
    body = _get("/healthz")
    assert body.get("status") == "ok", f"Unexpected body: {body}"


def test_readyz():
    """GET /readyz returns 200 + {"status": "ready"}."""
    body = _get("/readyz")
    assert body.get("status") == "ready", f"Unexpected body: {body}"


def test_root_has_version():
    """GET / response contains a 'version' key."""
    body = _get("/")
    assert "version" in body, f"'version' key missing from root response: {body}"


def test_generate_sync_explicit():
    """POST /generate/sync with explicit aws+snowflake+airflow stack returns 200."""
    body = _post(
        "/generate/sync",
        {"source": "snowflake", "orchestrator": "airflow", "infrastructure": "aws"},
    )
    # Response must be a dict (successful generation payload)
    assert isinstance(body, dict), f"Expected dict response, got: {type(body)}"


def test_generate_sync_recommended():
    """POST /generate/sync with mode=recommended returns 200."""
    body = _post("/generate/sync", {"mode": "recommended"})
    assert isinstance(body, dict), f"Expected dict response, got: {type(body)}"


def test_dbt_generate():
    """POST /dbt/generate returns file_count > 0."""
    body = _post("/dbt/generate", {"source": "snowflake", "project_name": "integration_test"})
    assert "file_count" in body, f"'file_count' missing: {body}"
    assert body["file_count"] > 0, f"Expected file_count > 0, got: {body['file_count']}"


def test_airflow_generate():
    """POST /dags/airflow/generate returns dag_count > 0."""
    body = _post("/dags/airflow/generate", {"source": "snowflake", "project_name": "integration_test"})
    assert "dag_count" in body, f"'dag_count' missing: {body}"
    assert body["dag_count"] > 0, f"Expected dag_count > 0, got: {body['dag_count']}"


def test_terraform_generate():
    """POST /terraform/generate returns file_count > 0."""
    body = _post("/terraform/generate", {"infrastructure": "aws", "project_name": "integration_test"})
    assert "file_count" in body, f"'file_count' missing: {body}"
    assert body["file_count"] > 0, f"Expected file_count > 0, got: {body['file_count']}"


def test_jobs_list():
    """GET /jobs returns a JSON list."""
    body = _get("/jobs")
    assert isinstance(body, list), f"Expected list, got: {type(body)}: {body}"


def test_async_job_flow():
    """POST /generate submits an async job; poll GET /jobs/{id} until completed (60s timeout)."""
    # Submit async job
    body = _post(
        "/generate",
        {"source": "snowflake", "orchestrator": "airflow", "infrastructure": "aws"},
    )
    assert "job_id" in body or "id" in body, f"No job id in response: {body}"
    job_id = body.get("job_id") or body.get("id")

    # Poll until completed or timeout
    deadline = time.time() + 60
    while time.time() < deadline:
        status_body = _get(f"/jobs/{job_id}")
        state = status_body.get("status") or status_body.get("state", "")
        if state in ("completed", "done", "success"):
            return  # test passes
        if state in ("failed", "error"):
            pytest.fail(f"Job {job_id} ended in error state: {status_body}")
        time.sleep(2)

    pytest.fail(f"Job {job_id} did not complete within 60 seconds")
