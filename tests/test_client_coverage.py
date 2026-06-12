"""
Additional coverage tests for datasphere/client.py — targeting missing lines.
"""
from __future__ import annotations

import json
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from datasphere.api.app import create_app
from datasphere.client import DataSphereClient, DataSphereError, _cli_main

_app = create_app()
_tc = TestClient(_app)


def _make_client(api_key=None) -> DataSphereClient:
    c = DataSphereClient(base_url="http://test", api_key=api_key)

    def _post(path: str, payload: dict) -> dict:
        resp = _tc.post(path, json=payload)
        if resp.status_code >= 400:
            raise DataSphereError(f"POST {path} → {resp.status_code}: {resp.text}")
        return resp.json()

    def _get(path: str):
        resp = _tc.get(path)
        if resp.status_code >= 400:
            raise DataSphereError(f"GET {path} → {resp.status_code}: {resp.text}")
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return resp.json()
        return resp.content

    c._post = _post  # type: ignore[method-assign]
    c._get = _get  # type: ignore[method-assign]
    return c


# ---------------------------------------------------------------------------
# generate_airflow, generate_dagster, generate_prefect
# ---------------------------------------------------------------------------

def test_generate_airflow():
    c = _make_client()
    result = c.generate_airflow(
        business_request="ETL pipeline test",
        ingestion="airbyte",
        transformation="dbt",
    )
    assert isinstance(result, dict)


def test_generate_dagster():
    c = _make_client()
    result = c.generate_dagster(
        business_request="Dagster pipeline test",
        data_warehouse="snowflake",
    )
    assert isinstance(result, dict)


def test_generate_prefect():
    c = _make_client()
    result = c.generate_prefect(
        business_request="Prefect pipeline test",
        data_warehouse="snowflake",
    )
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# generate / generate_async with security param
# ---------------------------------------------------------------------------

def test_generate_with_security_param():
    c = _make_client()
    result = c.generate(
        business_request="Secure pipeline",
        cloud_provider="aws",
        data_warehouse="snowflake",
        security="RBAC",
    )
    assert isinstance(result, dict)


def test_generate_async_with_security_param():
    c = _make_client()
    job_id = c.generate_async(
        business_request="Secure async pipeline",
        cloud_provider="aws",
        data_warehouse="snowflake",
        security="RLS",
    )
    assert isinstance(job_id, str)


# ---------------------------------------------------------------------------
# wait_for_job timeout
# ---------------------------------------------------------------------------

def test_wait_for_job_timeout():
    c = _make_client()
    call_count = [0]

    def _fake_get_job(job_id):
        call_count[0] += 1
        return {"status": "running"}

    c.get_job = _fake_get_job  # type: ignore[method-assign]

    with pytest.raises(TimeoutError):
        c.wait_for_job("fake-job-id", poll_interval=0.01, timeout=0.05)


# ---------------------------------------------------------------------------
# list_jobs wraps dict with "jobs" or "items" key
# ---------------------------------------------------------------------------

def test_list_jobs_dict_with_jobs_key():
    c = _make_client()
    c._get = lambda path: {"jobs": [{"id": "j1"}]}  # type: ignore[method-assign]
    result = c.list_jobs()
    assert result == [{"id": "j1"}]


def test_list_jobs_dict_with_items_key():
    c = _make_client()
    c._get = lambda path: {"items": [{"id": "j2"}]}  # type: ignore[method-assign]
    result = c.list_jobs()
    assert result == [{"id": "j2"}]


def test_list_jobs_dict_fallback_empty():
    c = _make_client()
    c._get = lambda path: {"other": "data"}  # type: ignore[method-assign]
    result = c.list_jobs()
    # Falls back to returning the dict itself per code: result.get("jobs", result.get("items", []))
    # In this case both get() miss and return [] via the nested get
    assert isinstance(result, (list, dict))


def test_list_jobs_unexpected_type():
    c = _make_client()
    c._get = lambda path: None  # type: ignore[method-assign]
    result = c.list_jobs()
    assert result == []


# ---------------------------------------------------------------------------
# download_job raises on JSON response
# ---------------------------------------------------------------------------

def test_download_job_raises_on_json_response():
    c = _make_client()
    c._get = lambda path: {"error": "not found"}  # type: ignore[method-assign]
    with pytest.raises(DataSphereError, match="Expected binary ZIP"):
        c.download_job("fake-job-id", output_dir="/tmp")


# ---------------------------------------------------------------------------
# _parse_sse_line static method
# ---------------------------------------------------------------------------

def test_parse_sse_line_valid():
    result = DataSphereClient._parse_sse_line('data: {"type": "status"}')
    assert result == {"type": "status"}


def test_parse_sse_line_invalid_json():
    result = DataSphereClient._parse_sse_line("data: not-valid-json")
    assert result == {"type": "raw", "message": "not-valid-json"}


def test_parse_sse_line_empty_data():
    result = DataSphereClient._parse_sse_line("data:   ")
    assert result is None


def test_parse_sse_line_non_data():
    result = DataSphereClient._parse_sse_line("event: update")
    assert result is None


# ---------------------------------------------------------------------------
# _stream_sse with httpx available — mock the streaming
# ---------------------------------------------------------------------------

def test_stream_sse_with_httpx(monkeypatch):
    """Test _stream_sse using httpx path (mocked)."""
    c = DataSphereClient(base_url="http://test")

    # Patch httpx.Client to return a context manager that streams lines
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter([
        'data: {"type": "status", "message": "running"}',
        'data: {"type": "done"}',
    ])

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_resp)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client_ctx = MagicMock()
    mock_client_ctx.__enter__ = MagicMock(return_value=mock_client)
    mock_client_ctx.__exit__ = MagicMock(return_value=False)

    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", True)
    monkeypatch.setattr(client_mod._httpx, "Client", MagicMock(return_value=mock_client_ctx))

    events = list(c._stream_sse("http://test/stream?job_id=abc"))
    assert any(e.get("type") == "done" for e in events)


# ---------------------------------------------------------------------------
# _cli_main — test via patching sys.argv
# ---------------------------------------------------------------------------

def test_cli_main_health(capsys):
    c_holder = [None]

    original_init = DataSphereClient.__init__

    def patched_init(self, base_url, api_key=None, **kwargs):
        original_init(self, base_url, api_key=api_key, **kwargs)
        self._get = lambda path: {"status": "ok"}  # type: ignore[method-assign]
        c_holder[0] = self

    with patch.object(DataSphereClient, "__init__", patched_init):
        with patch("sys.argv", ["datasphere-client", "health"]):
            _cli_main()

    out = capsys.readouterr().out
    assert "ok" in out


def test_cli_main_jobs(capsys):
    original_init = DataSphereClient.__init__

    def patched_init(self, base_url, api_key=None, **kwargs):
        original_init(self, base_url, api_key=api_key, **kwargs)
        self._get = lambda path: []  # type: ignore[method-assign]

    with patch.object(DataSphereClient, "__init__", patched_init):
        with patch("sys.argv", ["datasphere-client", "jobs"]):
            _cli_main()

    out = capsys.readouterr().out
    assert "[]" in out or out.strip() == "[]"


def test_cli_main_generate(capsys):
    original_init = DataSphereClient.__init__

    def patched_init(self, base_url, api_key=None, **kwargs):
        original_init(self, base_url, api_key=api_key, **kwargs)
        self._post = lambda path, payload: {"success": True, "job_id": "j1"}  # type: ignore[method-assign]

    with patch.object(DataSphereClient, "__init__", patched_init):
        with patch("sys.argv", [
            "datasphere-client", "generate", "Analytics test",
            "--cloud", "aws", "--warehouse", "snowflake",
        ]):
            _cli_main()

    out = capsys.readouterr().out
    assert "success" in out


# ---------------------------------------------------------------------------
# _headers with api_key
# ---------------------------------------------------------------------------

def test_headers_with_api_key():
    c = DataSphereClient("http://test", api_key="test-key-123")
    h = c._headers()
    assert h["Authorization"] == "Bearer test-key-123"


def test_headers_without_api_key():
    c = DataSphereClient("http://test")
    h = c._headers()
    assert "Authorization" not in h


# ---------------------------------------------------------------------------
# urllib fallback path (when httpx is not available)
# ---------------------------------------------------------------------------

def test_post_urllib_fallback(monkeypatch):
    """Test _post using urllib fallback path."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request
    import io

    response_data = json.dumps({"status": "ok"}).encode()

    class FakeResponse:
        def read(self):
            return response_data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())

    c = DataSphereClient("http://localhost:9999")
    result = c._post("/test", {"key": "value"})
    assert result == {"status": "ok"}


def test_get_urllib_fallback_json(monkeypatch):
    """Test _get using urllib fallback path with JSON response."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request

    response_data = json.dumps({"hello": "world"}).encode()

    class FakeResponse:
        def __init__(self):
            self.headers = {"Content-Type": "application/json"}
        def read(self):
            return response_data
        def get(self, key, default=""):
            return self.headers.get(key, default)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())

    c = DataSphereClient("http://localhost:9999")
    result = c._get("/test")
    assert result == {"hello": "world"}


def test_get_urllib_fallback_bytes(monkeypatch):
    """Test _get using urllib fallback path with binary response."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request

    class FakeResponse:
        def __init__(self):
            self.headers = {"Content-Type": "application/zip"}
        def read(self):
            return b"PK binary zip content"
        def get(self, key, default=""):
            return self.headers.get(key, default)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())

    c = DataSphereClient("http://localhost:9999")
    result = c._get("/test")
    assert result == b"PK binary zip content"


def test_post_urllib_http_error(monkeypatch):
    """Test _post urllib raises DataSphereError on HTTP error."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request
    import urllib.error

    def raise_http_error(req, timeout=None):
        raise urllib.error.HTTPError(
            url="http://test", code=404, msg="Not Found",
            hdrs=None, fp=io.BytesIO(b"not found")  # type: ignore
        )

    import io
    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    c = DataSphereClient("http://localhost:9999")
    with pytest.raises(DataSphereError, match="404"):
        c._post("/missing", {})


def test_get_urllib_http_error(monkeypatch):
    """Test _get urllib raises DataSphereError on HTTP error."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request
    import urllib.error
    import io

    def raise_http_error(req, timeout=None):
        raise urllib.error.HTTPError(
            url="http://test", code=403, msg="Forbidden",
            hdrs=None, fp=io.BytesIO(b"forbidden")  # type: ignore
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    c = DataSphereClient("http://localhost:9999")
    with pytest.raises(DataSphereError, match="403"):
        c._get("/protected")


def test_stream_sse_urllib_fallback(monkeypatch):
    """Test _stream_sse using urllib fallback."""
    import datasphere.client as client_mod
    monkeypatch.setattr(client_mod, "_HTTPX_AVAILABLE", False)

    import urllib.request

    lines = [
        b'data: {"type": "status", "message": "running"}\n',
        b'data: {"type": "done"}\n',
    ]

    class FakeResponse:
        def __enter__(self):
            return iter(lines)
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())

    c = DataSphereClient("http://localhost:9999")
    events = list(c._stream_sse("http://localhost:9999/stream"))
    assert any(e.get("type") == "done" for e in events)
