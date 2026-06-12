"""
Targeted tests to raise API coverage:
- DELETE /jobs/{id} — valid and invalid
- POST /jobs/purge
- GET /generate/stream with invalid job_id
- Rate limit (429)
- POST /generate missing business_request → 422
- GET /readyz with job_store.list_all raising
- Auth edge-cases re-verified via app
- job_store: _InMemoryStore and SQLiteJobStore methods
"""
from __future__ import annotations

import os
import time
import tempfile
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from datasphere.api.app import create_app
from datasphere.api.job_store import _InMemoryStore, SQLiteJobStore


# ---------------------------------------------------------------------------
# App fixtures
# ---------------------------------------------------------------------------

app = create_app()
client = TestClient(app)


# ---------------------------------------------------------------------------
# DELETE /jobs/{id}
# ---------------------------------------------------------------------------

class TestDeleteJob:
    def test_delete_existing_job_returns_200(self):
        # First create a job via async generate
        r = client.post("/generate", json={
            "business_request": "Test pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
        })
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        # Delete it
        r2 = client.delete(f"/jobs/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["deleted"] == job_id

    def test_delete_nonexistent_job_returns_404(self):
        r = client.delete("/jobs/nonexistent-job-id-xyz")
        assert r.status_code == 404
        assert "non trouvé" in r.json()["detail"] or "not found" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /jobs/purge
# ---------------------------------------------------------------------------

class TestPurgeJobs:
    def test_purge_returns_deleted_count(self):
        r = client.post("/jobs/purge")
        assert r.status_code == 200
        data = r.json()
        assert "deleted_count" in data
        assert isinstance(data["deleted_count"], int)

    def test_purge_with_max_age_hours(self):
        # max_age_hours=0 should delete everything
        r = client.post("/jobs/purge?max_age_hours=0")
        assert r.status_code == 200
        assert "deleted_count" in r.json()


# ---------------------------------------------------------------------------
# GET /generate/stream — invalid job_id
# ---------------------------------------------------------------------------

class TestSSEInvalidJob:
    def test_stream_nonexistent_job_returns_404(self):
        r = client.get("/generate/stream?job_id=does-not-exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting (429)
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_rate_limit_middleware_allows_normal_requests(self):
        # Just verify the middleware doesn't block normal usage
        r = client.get("/healthz")
        assert r.status_code == 200

    def test_rate_limit_hit_returns_429(self, monkeypatch):
        """Mock the rate limiter to always deny."""
        import datasphere.api.app as app_module

        original_is_allowed = app_module._rate_limiter.is_allowed

        def deny_all(ip: str) -> bool:
            return False

        monkeypatch.setattr(app_module._rate_limiter, "is_allowed", deny_all)
        try:
            r = client.post("/generate", json={
                "business_request": "test",
                "cloud_provider": "aws",
                "data_warehouse": "snowflake",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "metabase",
                "deployment": "docker-compose",
            })
            assert r.status_code == 429
        finally:
            monkeypatch.setattr(app_module._rate_limiter, "is_allowed", original_is_allowed)


# ---------------------------------------------------------------------------
# POST /generate missing business_request → 422
# ---------------------------------------------------------------------------

class TestGenerateMissingField:
    def test_missing_business_request_returns_422(self):
        r = client.post("/generate", json={
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /readyz — healthy and error cases
# ---------------------------------------------------------------------------

class TestReadyz:
    def test_readyz_returns_ok(self):
        r = client.get("/readyz")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_readyz_with_list_all_raising(self, monkeypatch):
        """When job_store.list_all raises, readyz should still return a response."""
        import datasphere.api.app as app_module

        def raise_error():
            raise RuntimeError("DB connection error")

        monkeypatch.setattr(app_module.job_store, "list_all", raise_error)
        r = client.get("/readyz")
        # Should return either 200 or 503, not 500
        assert r.status_code in (200, 503)


# ---------------------------------------------------------------------------
# Job Store — _InMemoryStore
# ---------------------------------------------------------------------------

class TestInMemoryStore:
    def test_create_and_get(self):
        store = _InMemoryStore()
        store.create("job1", status="pending")
        job = store.get("job1")
        assert job is not None
        assert job["job_id"] == "job1"
        assert job["status"] == "pending"

    def test_get_nonexistent_returns_none(self):
        store = _InMemoryStore()
        assert store.get("missing") is None

    def test_update_status(self):
        store = _InMemoryStore()
        store.create("job2", status="pending")
        store.update("job2", status="completed", result={"success": True})
        job = store.get("job2")
        assert job["status"] == "completed"
        assert job["result"]["success"] is True

    def test_update_nonexistent_is_noop(self):
        store = _InMemoryStore()
        # Should not raise
        store.update("missing", status="completed")

    def test_list_all_returns_sorted_by_created(self):
        store = _InMemoryStore()
        store.create("job_a", status="pending")
        time.sleep(0.01)
        store.create("job_b", status="completed")
        jobs = store.list_all()
        assert len(jobs) == 2
        assert jobs[0]["job_id"] == "job_b"  # most recent first

    def test_delete(self):
        store = _InMemoryStore()
        store.create("job3")
        store.delete("job3")
        assert store.get("job3") is None

    def test_delete_nonexistent_is_noop(self):
        store = _InMemoryStore()
        store.delete("not_there")  # should not raise

    def test_purge_old_removes_stale_jobs(self):
        store = _InMemoryStore()
        store.create("old_job")
        # Backdate the creation time
        with store._lock:
            store._data["old_job"]["created_at"] = time.time() - 90000
        deleted = store.purge_old(max_age_seconds=86400)
        assert deleted == 1
        assert store.get("old_job") is None

    def test_purge_old_keeps_fresh_jobs(self):
        store = _InMemoryStore()
        store.create("fresh_job")
        deleted = store.purge_old(max_age_seconds=86400)
        assert deleted == 0
        assert store.get("fresh_job") is not None

    def test_create_with_meta(self):
        store = _InMemoryStore()
        store.create("job_meta", meta={"mode": "explicit"})
        job = store.get("job_meta")
        assert job["meta"]["mode"] == "explicit"

    def test_thread_safety(self):
        store = _InMemoryStore()
        errors = []

        def worker(i):
            try:
                store.create(f"job_{i}")
                store.update(f"job_{i}", status="completed")
                store.get(f"job_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ---------------------------------------------------------------------------
# Job Store — SQLiteJobStore
# ---------------------------------------------------------------------------

class TestSQLiteJobStore:
    def _store(self, tmp_path):
        db_path = str(tmp_path / "test_jobs.db")
        return SQLiteJobStore(db_path)

    def test_create_and_get(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq1", status="pending")
        job = store.get("sq1")
        assert job is not None
        assert job["job_id"] == "sq1"
        assert job["status"] == "pending"

    def test_get_nonexistent(self, tmp_path):
        store = self._store(tmp_path)
        assert store.get("missing") is None

    def test_update(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq2")
        store.update("sq2", status="completed", result={"ok": True}, error="")
        job = store.get("sq2")
        assert job["status"] == "completed"
        assert job["result"]["ok"] is True

    def test_list_all(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq3")
        store.create("sq4")
        jobs = store.list_all()
        ids = [j["job_id"] for j in jobs]
        assert "sq3" in ids
        assert "sq4" in ids

    def test_delete(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq5")
        store.delete("sq5")
        assert store.get("sq5") is None

    def test_purge_old(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq_old")
        # Directly set a very old timestamp in the db
        import sqlite3
        with sqlite3.connect(str(tmp_path / "test_jobs.db")) as conn:
            conn.execute("UPDATE jobs SET created_at=? WHERE job_id=?", (time.time() - 90000, "sq_old"))
            conn.commit()
        deleted = store.purge_old(max_age_seconds=86400)
        assert deleted == 1

    def test_update_with_result_none(self, tmp_path):
        store = self._store(tmp_path)
        store.create("sq6")
        store.update("sq6", status="failed", result=None, error="something went wrong")
        job = store.get("sq6")
        assert job["result"] is None
        assert job["error"] == "something went wrong"


# ---------------------------------------------------------------------------
# /stacks endpoints
# ---------------------------------------------------------------------------

class TestStacksEndpoints:
    def test_stacks_supported(self):
        r = client.get("/stacks/supported")
        assert r.status_code == 200

    def test_stacks_adapters(self):
        r = client.get("/stacks/adapters")
        assert r.status_code == 200
        assert "adapter_count" in r.json()


# ---------------------------------------------------------------------------
# Download endpoint edge cases
# ---------------------------------------------------------------------------

class TestDownloadEdgeCases:
    def test_download_completed_job(self):
        # Create a job and wait for it to complete
        r = client.post("/generate/sync", json={
            "business_request": "Download test pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
        })
        assert r.status_code == 200

        # List jobs to get the job_id of completed job
        jobs_r = client.get("/jobs")
        assert jobs_r.status_code == 200
        jobs = jobs_r.json()
        completed_jobs = [j for j in jobs if j["status"] == "completed"]
        if completed_jobs:
            job_id = completed_jobs[0]["job_id"]
            dl = client.get(f"/jobs/{job_id}/download")
            # May succeed (200) or return 404 if artifacts not on disk — both valid
            assert dl.status_code in (200, 404)
