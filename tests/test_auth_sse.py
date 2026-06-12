"""Tests pour l'authentification Bearer et le streaming SSE."""
from __future__ import annotations
import os
import pytest
from fastapi.testclient import TestClient


def _make_client(api_key: str | None = None):
    if api_key is not None:
        os.environ["DATASPHERE_API_KEY"] = api_key
    elif "DATASPHERE_API_KEY" in os.environ:
        del os.environ["DATASPHERE_API_KEY"]
    # Reload auth module to pick up env change
    import importlib
    import datasphere.api.auth as auth_mod
    importlib.reload(auth_mod)
    import datasphere.api.app as app_mod
    importlib.reload(app_mod)
    return TestClient(app_mod.app)


# ---------------------------------------------------------------------------
# Auth disabled (no env var)
# ---------------------------------------------------------------------------

class TestAuthDisabled:

    def setup_method(self):
        if "DATASPHERE_API_KEY" in os.environ:
            del os.environ["DATASPHERE_API_KEY"]
        from datasphere.api.app import app
        self.client = TestClient(app)

    def test_health_no_auth(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        assert r.json()["auth_enabled"] is False

    def test_generate_sync_no_auth_required(self):
        payload = {
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
        r = self.client.post("/generate/sync", json=payload)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth enabled
# ---------------------------------------------------------------------------

class TestAuthEnabled:
    SECRET = "super-secret-key-42"

    def setup_method(self):
        os.environ["DATASPHERE_API_KEY"] = self.SECRET
        import importlib, datasphere.api.auth as auth_mod, datasphere.api.app as app_mod
        importlib.reload(auth_mod)
        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def teardown_method(self):
        if "DATASPHERE_API_KEY" in os.environ:
            del os.environ["DATASPHERE_API_KEY"]

    def test_health_shows_auth_enabled(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        assert r.json()["auth_enabled"] is True

    def test_generate_sync_without_token_returns_401(self):
        payload = {
            "mode": "explicit",
            "business_request": "Test",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
        }
        r = self.client.post("/generate/sync", json=payload)
        assert r.status_code == 401

    def test_generate_sync_with_wrong_token_returns_401(self):
        payload = {
            "mode": "explicit",
            "business_request": "Test",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
        }
        r = self.client.post(
            "/generate/sync",
            json=payload,
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401

    def test_generate_sync_with_correct_token(self):
        payload = {
            "mode": "explicit",
            "business_request": "Test",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
        }
        r = self.client.post(
            "/generate/sync",
            json=payload,
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        assert r.status_code == 200

    def test_unprotected_endpoints_accessible_without_token(self):
        """Health, docs, stacks catalog — no auth required."""
        assert self.client.get("/health").status_code == 200
        assert self.client.get("/stacks/supported").status_code == 200
        assert self.client.get("/stacks/adapters").status_code == 200


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------

class TestSSEStreaming:

    def setup_method(self):
        if "DATASPHERE_API_KEY" in os.environ:
            del os.environ["DATASPHERE_API_KEY"]
        from datasphere.api.app import app
        self.client = TestClient(app)

    def test_stream_unknown_job_returns_404(self):
        r = self.client.get("/generate/stream?job_id=nonexistent-uuid")
        assert r.status_code == 404

    def test_stream_completed_job_returns_done_event(self):
        from datasphere.api.job_store import job_store
        import uuid
        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="completed")
        job_store.update(job_id, status="completed", result={"success": True})

        with self.client.stream("GET", f"/generate/stream?job_id={job_id}") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = resp.read().decode()
        assert '"type": "done"' in body
        assert '"success": true' in body

    def test_stream_failed_job_returns_error_event(self):
        from datasphere.api.job_store import job_store
        import uuid
        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="failed")
        job_store.update(job_id, status="failed", error="something went wrong")

        with self.client.stream("GET", f"/generate/stream?job_id={job_id}") as resp:
            assert resp.status_code == 200
            body = resp.read().decode()
        assert '"type": "error"' in body
        assert "something went wrong" in body

    def test_stream_pending_job_emits_status(self):
        from datasphere.api.job_store import job_store
        import uuid, threading, time
        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="pending")

        # Complete the job from another thread after a short delay
        def complete():
            time.sleep(0.5)
            job_store.update(job_id, status="completed", result={"ok": True})

        t = threading.Thread(target=complete)
        t.start()

        with self.client.stream("GET", f"/generate/stream?job_id={job_id}") as resp:
            body = resp.read().decode()
        t.join()

        assert '"type": "status"' in body
        assert '"type": "done"' in body
