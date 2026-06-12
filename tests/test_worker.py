"""Tests for the optional ARQ worker module (datasphere/api/worker.py)."""
from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_worker():
    """Reload the worker module so env-var changes take effect."""
    mod_name = "datasphere.api.worker"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# enqueue_generation — returns None when Redis not configured
# ---------------------------------------------------------------------------

class TestEnqueueGeneration:
    def test_returns_none_when_no_redis_url(self, monkeypatch):
        """enqueue_generation must return None when DATASPHERE_REDIS_URL is not set."""
        monkeypatch.delenv("DATASPHERE_REDIS_URL", raising=False)
        worker = _reload_worker()

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.enqueue_generation("job-123", {"mode": "explicit"})
        )
        assert result is None

    def test_returns_none_when_arq_not_available(self, monkeypatch):
        """enqueue_generation must return None when arq is not installed."""
        monkeypatch.setenv("DATASPHERE_REDIS_URL", "redis://localhost:6379")
        worker = _reload_worker()
        # Patch _ARQ_AVAILABLE to False to simulate missing install
        monkeypatch.setattr(worker, "_ARQ_AVAILABLE", False)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.enqueue_generation("job-123", {"mode": "explicit"})
        )
        assert result is None

    def test_returns_none_when_redis_url_empty_string(self, monkeypatch):
        """enqueue_generation must return None when DATASPHERE_REDIS_URL is empty."""
        monkeypatch.setenv("DATASPHERE_REDIS_URL", "")
        worker = _reload_worker()

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            worker.enqueue_generation("job-456", {})
        )
        assert result is None


# ---------------------------------------------------------------------------
# WorkerSettings
# ---------------------------------------------------------------------------

class TestWorkerSettings:
    def test_functions_list_contains_run_generation_job(self):
        """WorkerSettings.functions must include run_generation_job."""
        worker = _reload_worker()
        assert worker.run_generation_job in worker.WorkerSettings.functions

    def test_functions_list_length(self):
        """WorkerSettings.functions must contain exactly one function."""
        worker = _reload_worker()
        assert len(worker.WorkerSettings.functions) == 1

    def test_redis_settings_property_uses_env(self, monkeypatch):
        """WorkerSettings.redis_settings uses DATASPHERE_REDIS_URL."""
        monkeypatch.setenv("DATASPHERE_REDIS_URL", "redis://myredis:6380")
        worker = _reload_worker()
        if not worker._ARQ_AVAILABLE:
            pytest.skip("arq not installed")
        settings = worker.WorkerSettings()
        rs = settings.redis_settings
        # RedisSettings.from_dsn parses host / port
        assert rs.host == "myredis"
        assert rs.port == 6380


# ---------------------------------------------------------------------------
# run_generation_job — calls _run_generation with correct args
# ---------------------------------------------------------------------------

class TestRunGenerationJob:
    def test_calls_run_generation_with_correct_args(self, monkeypatch):
        """run_generation_job must deserialise req_dict and call _run_generation."""
        import asyncio
        worker = _reload_worker()

        req_dict = {
            "mode": "explicit",
            "business_request": "Test pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
        }

        captured = {}

        def fake_run_generation(job_id, req):
            captured["job_id"] = job_id
            captured["req"] = req

        # Patch _run_generation in app module
        import datasphere.api.app as app_mod
        monkeypatch.setattr(app_mod, "_run_generation", fake_run_generation)

        ctx: dict = {}
        asyncio.get_event_loop().run_until_complete(
            worker.run_generation_job(ctx, "test-job-id", req_dict)
        )

        assert captured["job_id"] == "test-job-id"
        assert captured["req"].mode == "explicit"
        assert captured["req"].business_request == "Test pipeline"

    def test_run_generation_job_passes_req_dict_fields(self, monkeypatch):
        """run_generation_job correctly maps all provided req_dict fields."""
        import asyncio
        worker = _reload_worker()

        req_dict = {
            "mode": "recommended",
            "business_request": "Analytics startup",
            "budget": "low",
        }

        results = {}

        def fake_run(job_id, req):
            results["mode"] = req.mode
            results["budget"] = req.budget

        import datasphere.api.app as app_mod
        monkeypatch.setattr(app_mod, "_run_generation", fake_run)

        asyncio.get_event_loop().run_until_complete(
            worker.run_generation_job({}, "job-999", req_dict)
        )

        assert results["mode"] == "recommended"
        assert results["budget"] == "low"
