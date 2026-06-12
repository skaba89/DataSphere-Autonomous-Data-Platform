"""Tests for per-endpoint rate limiting."""
from __future__ import annotations

import importlib
import sys
import types
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers to reset module-level state between tests
# ---------------------------------------------------------------------------

def _fresh_app():
    """Re-import datasphere.api.app to get a clean limiter state."""
    # Remove cached module so limiters are recreated
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("datasphere.api.app"):
            del sys.modules[mod_name]
    from datasphere.api.app import create_app, _endpoint_limiters
    # Clear lazily created limiters between tests
    _endpoint_limiters.clear()
    return create_app()


def _make_client(app, ip: str = "1.2.3.4") -> TestClient:
    """Return a TestClient that spoofs the given remote IP."""
    client = TestClient(app, raise_server_exceptions=True)
    # Monkeypatch transport so request.client.host returns our IP
    original_send = client._transport.handle_request

    def _patched_send(request):
        # httpx ASGI transport stores scope; inject client address
        return original_send(request)

    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_limiters():
    """Clear per-endpoint limiter windows before each test."""
    # Import after any previous test may have set things up
    try:
        from datasphere.api import app as app_module
        app_module._endpoint_limiters.clear()
        # Also clear internal windows of the limiters
        for limiter in app_module._endpoint_limiters.values():
            with limiter._lock:
                limiter._windows.clear()
        # Reset the global limiter too
        with app_module._rate_limiter._lock:
            app_module._rate_limiter._windows.clear()
    except Exception:
        pass
    yield
    try:
        from datasphere.api import app as app_module
        app_module._endpoint_limiters.clear()
        for limiter in app_module._endpoint_limiters.values():
            with limiter._lock:
                limiter._windows.clear()
        with app_module._rate_limiter._lock:
            app_module._rate_limiter._windows.clear()
    except Exception:
        pass


@pytest.fixture()
def app():
    from datasphere.api.app import app as _app
    return _app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(client: TestClient, path: str, ip: str = "1.2.3.4", **kwargs):
    """POST with a spoofed X-Forwarded-For / client IP header."""
    headers = kwargs.pop("headers", {})
    headers["X-Forwarded-For"] = ip
    # TestClient ASGI uses the loopback address; we override the rate-key via
    # the actual host that reaches the middleware. Since TestClient always uses
    # 127.0.0.1 as request.client.host, we need to patch _check_endpoint_limit
    # to use the header — but the implementation uses request.client.host.
    # Instead we manipulate the limiter windows directly.
    return client.post(path, headers=headers, **kwargs)


def _drain_endpoint(path: str, ip: str, limit: int):
    """Consume all tokens for (path, ip) by directly manipulating the limiter."""
    import time
    from datasphere.api.app import _endpoint_limiters, _ENDPOINT_LIMITS

    # Normalise path
    lookup = path[3:] if path.startswith("/v1") else path
    rpm = _ENDPOINT_LIMITS.get(lookup, 0)
    if not rpm:
        return

    from datasphere.api.app import _RateLimiter
    # Ensure limiter exists
    from datasphere.api import app as app_module
    with app_module._endpoint_limiters_lock:
        if lookup not in app_module._endpoint_limiters:
            app_module._endpoint_limiters[lookup] = _RateLimiter(rpm)
        limiter = app_module._endpoint_limiters[lookup]

    now = time.monotonic()
    with limiter._lock:
        # Fill the window with `limit` timestamps so next call is rejected
        limiter._windows[ip] = [now] * limit


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEndpointRateLimits:
    """Verify per-endpoint limits are enforced independently of global limit."""

    def test_generate_allows_up_to_limit(self, client):
        """The /generate endpoint should allow exactly 10 requests per IP."""
        from datasphere.api import app as app_module
        ip = "testclient"  # matches request.client.host in TestClient

        # Drain 9 tokens — leaving 1 remaining
        _drain_endpoint("/generate", ip, 9)

        # One more should still be allowed (hits real endpoint → 422 not 429)
        resp = client.post(
            "/generate",
            json={"business_request": "test"},
        )
        assert resp.status_code != 429, f"Expected not 429, got {resp.status_code}"

    def test_generate_blocks_11th_request(self, client):
        """The 11th request to /generate from the same IP must return 429."""
        ip = "testclient"
        _drain_endpoint("/generate", ip, 10)

        resp = client.post(
            "/generate",
            json={"business_request": "test"},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body.get("error") == "rate_limit_exceeded"
        assert "/generate" in body.get("endpoint", "")

    def test_generate_sync_blocks_6th_request(self, client):
        """The 6th request to /generate/sync must return 429 (limit=5)."""
        ip = "testclient"
        _drain_endpoint("/generate/sync", ip, 5)

        resp = client.post(
            "/generate/sync",
            json={"business_request": "test"},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body.get("error") == "rate_limit_exceeded"
        assert "generate/sync" in body.get("endpoint", "")

    def test_different_ips_have_independent_counters(self, client):
        """Draining one IP's bucket must not affect another IP."""
        from datasphere.api import app as app_module

        ip_a = "default:10.0.0.1"
        ip_b = "default:10.0.0.2"

        # Drain IP A completely
        _drain_endpoint("/generate", ip_a, 10)

        # IP A should be blocked
        # Manipulate the global limiter too so it won't block IP B
        # We test by checking the endpoint limiter directly
        lookup = "/generate"
        with app_module._endpoint_limiters_lock:
            limiter = app_module._endpoint_limiters.get(lookup)
        assert limiter is not None

        # IP B should still be allowed
        allowed_b = limiter.is_allowed(ip_b)
        assert allowed_b is True

        # IP A should be denied
        allowed_a = limiter.is_allowed(ip_a)
        assert allowed_a is False

    def test_global_limit_still_triggers_for_unspecified_endpoints(self, client):
        """Global rate limiter (60 RPM) applies to endpoints not in _ENDPOINT_LIMITS."""
        from datasphere.api import app as app_module
        import time

        ip = "testclient"
        # Fill global limiter for this IP
        now = time.monotonic()
        with app_module._rate_limiter._lock:
            app_module._rate_limiter._windows[f"default:{ip}"] = [now] * 60

        # /dbt/generate is not in _ENDPOINT_LIMITS — should hit global limit
        resp = client.post(
            "/dbt/generate",
            json={
                "business_request": "test pipeline",
                "cloud_provider": "aws",
                "data_warehouse": "snowflake",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "superset",
                "deployment": "kubernetes",
            },
        )
        assert resp.status_code == 429

    def test_429_response_includes_retry_after(self, client):
        """429 response from endpoint limit must include retry_after field."""
        ip = "testclient"
        _drain_endpoint("/proposals", ip, 20)

        resp = client.post(
            "/proposals",
            json={},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)
        assert body["retry_after"] >= 1

    def test_endpoint_limits_env_override(self, monkeypatch):
        """DATASPHERE_ENDPOINT_RATE_LIMITS env var merges into _ENDPOINT_LIMITS."""
        monkeypatch.setenv("DATASPHERE_ENDPOINT_RATE_LIMITS", '{"generate": 20}')

        # Re-import module to pick up env var
        for mod_name in list(sys.modules.keys()):
            if "datasphere.api.app" in mod_name:
                del sys.modules[mod_name]

        from datasphere.api.app import _ENDPOINT_LIMITS
        assert _ENDPOINT_LIMITS.get("/generate") == 20

        # Restore original value for other tests
        for mod_name in list(sys.modules.keys()):
            if "datasphere.api.app" in mod_name:
                del sys.modules[mod_name]
        monkeypatch.delenv("DATASPHERE_ENDPOINT_RATE_LIMITS", raising=False)
        import datasphere.api.app  # re-import without override


class TestCheckEndpointLimit:
    """Unit tests for _check_endpoint_limit helper."""

    def test_unknown_path_always_allowed(self):
        from datasphere.api import app as app_module
        app_module._endpoint_limiters.clear()

        allowed, rpm = app_module._check_endpoint_limit("/some/unknown/path", "1.2.3.4")
        assert allowed is True
        assert rpm == 0

    def test_v1_prefix_normalised(self):
        """Paths under /v1 are treated the same as their unprefixed counterparts."""
        from datasphere.api import app as app_module
        app_module._endpoint_limiters.clear()

        # /v1/generate should use the /generate limit
        allowed, rpm = app_module._check_endpoint_limit("/v1/generate", "1.2.3.4")
        assert rpm == app_module._ENDPOINT_LIMITS["/generate"]

    def test_limiter_created_lazily(self):
        from datasphere.api import app as app_module
        app_module._endpoint_limiters.clear()

        assert "/generate" not in app_module._endpoint_limiters
        app_module._check_endpoint_limit("/generate", "1.2.3.4")
        assert "/generate" in app_module._endpoint_limiters
