"""
Shared pytest fixtures and configuration.
"""
from __future__ import annotations
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Ensure auth is disabled by default for all tests."""
    monkeypatch.delenv("DATASPHERE_API_KEY", raising=False)


@pytest.fixture
def client():
    """FastAPI TestClient with auth disabled."""
    from datasphere.api.app import app
    return TestClient(app)


@pytest.fixture
def auth_client(monkeypatch):
    """TestClient with auth enabled and a known key."""
    monkeypatch.setenv("DATASPHERE_API_KEY", "test-secret-key")
    import importlib
    import datasphere.api.auth as auth_mod
    import datasphere.api.app as app_mod
    importlib.reload(auth_mod)
    importlib.reload(app_mod)
    return TestClient(app_mod.app), "test-secret-key"
