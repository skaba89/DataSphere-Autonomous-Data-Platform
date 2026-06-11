"""Tests for optional OpenTelemetry tracing module."""
from __future__ import annotations
import importlib
import sys
import types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_tracing():
    """Reload the tracing module so module-level globals reset."""
    if "datasphere.api.tracing" in sys.modules:
        del sys.modules["datasphere.api.tracing"]
    import datasphere.api.tracing as tracing
    return tracing


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tracing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DATASPHERE_OTLP_ENDPOINT", raising=False)
    tracing = _reload_tracing()
    tracing.setup_tracing("test-service")
    assert tracing.is_enabled() is False


def test_noop_span_context_manager():
    from datasphere.api.tracing import _NoopSpan
    span = _NoopSpan()
    with span as s:
        s.set_attribute("key", "value")
        s.record_exception(Exception("boom"))
        s.set_status("ERROR")
    # No exception raised means pass


def test_start_span_returns_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("DATASPHERE_OTLP_ENDPOINT", raising=False)
    tracing = _reload_tracing()
    span = tracing.start_span("test.span")
    from datasphere.api.tracing import _NoopSpan
    assert isinstance(span, _NoopSpan)


def test_get_tracer_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("DATASPHERE_OTLP_ENDPOINT", raising=False)
    tracing = _reload_tracing()
    assert tracing.get_tracer() is None


def test_get_trace_id_returns_empty_when_no_span():
    from datasphere.api.logging_config import _get_trace_id
    result = _get_trace_id()
    assert result == ""


def test_setup_tracing_with_endpoint_but_no_sdk(monkeypatch):
    """When endpoint is set but opentelemetry is not importable, no exception raised."""
    monkeypatch.setenv("DATASPHERE_OTLP_ENDPOINT", "http://localhost:4317")
    tracing = _reload_tracing()

    # Patch builtins.__import__ to raise ImportError for opentelemetry
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    tracing2 = _reload_tracing()
    # Should not raise
    tracing2.setup_tracing("test-service")
    assert tracing2.is_enabled() is False


def test_json_formatter_has_trace_id_field():
    import json
    import logging
    from datasphere.api.logging_config import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "trace_id" in parsed
    assert isinstance(parsed["trace_id"], str)


def test_app_starts_without_otel(monkeypatch):
    monkeypatch.delenv("DATASPHERE_OTLP_ENDPOINT", raising=False)
    from fastapi.testclient import TestClient
    from datasphere.api.app import create_app
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
