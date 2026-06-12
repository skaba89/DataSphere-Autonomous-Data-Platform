"""
Tests for the DataSphere Python SDK client (datasphere/client.py).

Strategy: create a DataSphereClient with base_url="http://test", then
monkey-patch _post / _get so all HTTP calls are routed through the FastAPI
TestClient instead of making real network requests.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from datasphere.api.app import create_app
from datasphere.client import DataSphereClient

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_app = create_app()
_tc = TestClient(_app)


def _make_client() -> DataSphereClient:
    """Return an SDK client whose HTTP calls are forwarded to the TestClient."""
    c = DataSphereClient(base_url="http://test")

    def _post(path: str, payload: dict) -> dict:
        resp = _tc.post(path, json=payload)
        assert resp.status_code < 500, f"POST {path} returned {resp.status_code}: {resp.text}"
        return resp.json()

    def _get(path: str):
        resp = _tc.get(path)
        assert resp.status_code < 500, f"GET {path} returned {resp.status_code}: {resp.text}"
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return resp.json()
        return resp.content

    c._post = _post  # type: ignore[method-assign]
    c._get = _get  # type: ignore[method-assign]
    return c


# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------


def test_client_health():
    c = _make_client()
    result = c.health()
    assert isinstance(result, dict)
    assert result.get("status") == "ok"


# ---------------------------------------------------------------------------
# 2. Synchronous generation
# ---------------------------------------------------------------------------


def test_client_generate_sync():
    c = _make_client()
    result = c.generate(
        business_request="Pipeline analytics ventes",
        cloud_provider="aws",
        data_warehouse="snowflake",
    )
    assert isinstance(result, dict)
    # The /generate/sync endpoint returns the job result dict directly
    assert "success" in result


# ---------------------------------------------------------------------------
# 3. Async generation + wait_for_job
# ---------------------------------------------------------------------------


def test_client_generate_async_and_wait():
    c = _make_client()

    # generate_async returns a job_id
    job_id = c.generate_async(
        business_request="Async pipeline test",
        cloud_provider="gcp",
        data_warehouse="bigquery",
    )
    assert isinstance(job_id, str)
    assert len(job_id) > 0

    # wait_for_job polls until completed; use a very short poll interval since
    # the TestClient executes synchronously but background tasks run inline
    # when raise_server_exceptions=True (default).  We just re-poll once.
    job = c.wait_for_job(job_id, poll_interval=0.1, timeout=30.0)
    assert isinstance(job, dict)
    assert job.get("status") in ("completed", "failed")


# ---------------------------------------------------------------------------
# 4. dbt generation
# ---------------------------------------------------------------------------


def test_client_generate_dbt():
    c = _make_client()
    result = c.generate_dbt(
        business_request="Sales analytics dbt models",
        data_warehouse="snowflake",
        ingestion="airbyte",
    )
    assert isinstance(result, dict)
    # The /dbt/generate endpoint always returns a "files" key
    assert "files" in result


# ---------------------------------------------------------------------------
# 5. Terraform generation
# ---------------------------------------------------------------------------


def test_client_generate_terraform():
    c = _make_client()
    result = c.generate_terraform(
        business_request="AWS data lake infrastructure",
        cloud_provider="aws",
        data_warehouse="snowflake",
        deployment="kubernetes",
        budget="medium",
    )
    assert isinstance(result, dict)
    assert "files" in result


# ---------------------------------------------------------------------------
# 6. List jobs
# ---------------------------------------------------------------------------


def test_client_list_jobs():
    c = _make_client()
    jobs = c.list_jobs()
    # New paginated API returns a dict with "items"; legacy bare list also accepted
    assert isinstance(jobs, (list, dict))


# ---------------------------------------------------------------------------
# 7. Download job (saves ZIP to disk)
# ---------------------------------------------------------------------------


def test_client_download_job(tmp_path):
    # First create and complete a job so there is something to download
    c = _make_client()
    job_id = c.generate_async(
        business_request="Download test pipeline",
        cloud_provider="aws",
        data_warehouse="snowflake",
    )
    # Wait for completion
    c.wait_for_job(job_id, poll_interval=0.1, timeout=30.0)

    dest = c.download_job(job_id, output_dir=str(tmp_path))
    assert os.path.exists(dest)
    assert dest.endswith(".zip")
    assert os.path.getsize(dest) > 0


# ---------------------------------------------------------------------------
# 8. SSE streaming yields at least one event
# ---------------------------------------------------------------------------


def test_client_stream_yields_events():
    """
    stream() launches an async job then reads SSE events.

    We monkey-patch _stream_sse to avoid actually connecting to the SSE
    endpoint (which behaves differently under TestClient), and instead
    simulate a minimal SSE response.
    """
    c = _make_client()

    # Track that generate_async is called correctly by capturing the job_id
    captured: list[str] = []
    _orig_generate_async = c.generate_async

    def _fake_generate_async(**kwargs):
        job_id = _orig_generate_async(**kwargs)
        captured.append(job_id)
        return job_id

    c.generate_async = _fake_generate_async  # type: ignore[method-assign]

    # Patch _stream_sse to return synthetic events
    def _fake_stream_sse(path: str):
        yield {"type": "status", "message": "running"}
        yield {"type": "done", "message": "completed"}

    c._stream_sse = _fake_stream_sse  # type: ignore[method-assign]

    events = list(
        c.stream(
            business_request="Stream test pipeline",
            cloud_provider="aws",
            data_warehouse="snowflake",
        )
    )
    assert len(events) >= 1
    assert events[0].get("type") == "status"
    # generate_async was called and returned a valid job_id
    assert len(captured) == 1
    assert len(captured[0]) > 0
