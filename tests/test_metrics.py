"""Tests for the Prometheus-compatible /metrics endpoint."""
from __future__ import annotations
import time

import pytest
from fastapi.testclient import TestClient

from datasphere.api.metrics import MetricsCollector, _Histogram
from datasphere.api.app import create_app


# ---------------------------------------------------------------------------
# Unit tests — MetricsCollector
# ---------------------------------------------------------------------------

def test_metrics_render_returns_string():
    mc = MetricsCollector()
    result = mc.render()
    assert isinstance(result, str)
    assert len(result) > 0


def test_metrics_has_datasphere_up():
    mc = MetricsCollector()
    result = mc.render()
    assert "datasphere_up 1" in result


def test_metrics_has_uptime():
    mc = MetricsCollector()
    result = mc.render()
    assert "datasphere_uptime_seconds" in result


def test_record_http_request_increments_counter():
    mc = MetricsCollector()
    mc.record_http_request("GET", "/health", 200, 0.01)
    mc.record_http_request("GET", "/health", 200, 0.02)
    result = mc.render()
    assert 'datasphere_http_requests_total{method="GET",path="/health",status="200"} 2' in result


def test_histogram_observe_increments_buckets():
    h = _Histogram()
    h.observe(0.05)
    # Buckets 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0 should be >= 1
    # Bucket 0.01 should remain 0
    assert h._counts[0] == 0   # le=0.01
    assert h._counts[1] == 1   # le=0.05
    assert h._counts[2] == 1   # le=0.1


def test_histogram_sum_tracks_values():
    h = _Histogram()
    h.observe(0.1)
    h.observe(0.3)
    assert abs(h._sum - 0.4) < 1e-9
    assert h._total == 2


def test_record_job_created_increments_counter():
    mc = MetricsCollector()
    mc.record_job_created(mode="explicit")
    mc.record_job_created(mode="explicit")
    result = mc.render()
    assert 'datasphere_jobs_created_total{mode="explicit"} 2' in result


def test_record_job_completed_increments_counter():
    mc = MetricsCollector()
    mc.record_job_completed(mode="explicit", duration_s=1.5)
    result = mc.render()
    assert 'datasphere_jobs_completed_total{mode="explicit"} 1' in result


def test_record_job_failed_increments_counter():
    mc = MetricsCollector()
    mc.record_job_failed(mode="recommended")
    result = mc.render()
    assert 'datasphere_jobs_failed_total{mode="recommended"} 1' in result


# ---------------------------------------------------------------------------
# Integration tests — FastAPI /metrics endpoint
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_api_metrics_endpoint_200(client):
    response = client.get("/metrics")
    assert response.status_code == 200


def test_api_metrics_content_type(client):
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]


def test_api_metrics_after_request_shows_counter(client):
    # Make a request so the counter has something
    client.get("/health")
    response = client.get("/metrics")
    body = response.text
    # At minimum the metrics endpoint itself was called — counter must be > 0
    assert "datasphere_http_requests_total" in body
    # Find any counter value > 0
    import re
    counts = re.findall(r"datasphere_http_requests_total\{[^}]+\} (\d+)", body)
    assert any(int(c) > 0 for c in counts)
