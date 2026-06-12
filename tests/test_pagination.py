"""Tests for pagination on GET /jobs and GET /artifacts/{job_id}."""
from __future__ import annotations
import time
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_seed_counter = 0


def _seed_jobs(store, n: int, status: str = "completed") -> list[str]:
    """Create n jobs with the given status directly in the job_store."""
    global _seed_counter
    ids = []
    for _ in range(n):
        _seed_counter += 1
        jid = f"test-pag-{_seed_counter:06d}"
        store.create(jid, status=status)
        if status != "pending":
            store.update(jid, status=status)
        ids.append(jid)
    return ids


@pytest.fixture
def fresh_store(monkeypatch):
    """Swap job_store for a clean in-memory store for each test."""
    from datasphere.api.job_store import _InMemoryStore
    import datasphere.api.app as app_mod
    import datasphere.api.job_store as store_mod

    fresh = _InMemoryStore()
    monkeypatch.setattr(store_mod, "job_store", fresh)
    monkeypatch.setattr(app_mod, "job_store", fresh)
    return fresh


@pytest.fixture
def client_with_store(fresh_store):
    from datasphere.api.app import app
    return TestClient(app), fresh_store


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------

class TestJobsPagination:

    def test_jobs_list_default_returns_dict_with_items(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 3)
        r = client.get("/jobs")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body

    def test_jobs_list_has_total_field(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 5)
        r = client.get("/jobs")
        body = r.json()
        assert "total" in body
        assert body["total"] == 5

    def test_jobs_list_has_more_false_when_empty(self, client_with_store):
        client, _ = client_with_store
        r = client.get("/jobs")
        body = r.json()
        assert body["has_more"] is False
        assert body["total"] == 0

    def test_jobs_list_limit_parameter(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 10)
        r = client.get("/jobs?limit=2")
        body = r.json()
        assert len(body["items"]) <= 2
        assert body["limit"] == 2

    def test_jobs_list_offset_parameter(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 5)
        r_all = client.get("/jobs?limit=50").json()
        r_offset = client.get("/jobs?limit=50&offset=2").json()
        # With offset=2 we should get fewer items
        assert r_offset["offset"] == 2
        assert len(r_offset["items"]) == len(r_all["items"]) - 2

    def test_jobs_list_status_filter_completed(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 3, status="completed")
        _seed_jobs(store, 2, status="failed")
        r = client.get("/jobs?status=completed")
        body = r.json()
        assert body["total"] == 3
        assert all(j["status"] == "completed" for j in body["items"])

    def test_jobs_list_status_filter_failed(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 3, status="completed")
        _seed_jobs(store, 2, status="failed")
        r = client.get("/jobs?status=failed")
        body = r.json()
        assert body["total"] == 2
        assert all(j["status"] == "failed" for j in body["items"])

    def test_jobs_list_status_filter_invalid(self, client_with_store):
        """Unknown status value should return empty items, not 422."""
        client, store = client_with_store
        _seed_jobs(store, 3)
        r = client.get("/jobs?status=nonexistent")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_jobs_list_has_more_true_when_more_items(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 5)
        r = client.get("/jobs?limit=2&offset=0")
        body = r.json()
        assert body["has_more"] is True

    def test_jobs_list_next_offset_set_when_has_more(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 5)
        r = client.get("/jobs?limit=2&offset=0")
        body = r.json()
        assert body["next_offset"] == 2

    def test_jobs_list_link_header_when_has_more(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 5)
        r = client.get("/jobs?limit=2&offset=0")
        assert "link" in {k.lower() for k in r.headers}
        link = r.headers.get("link") or r.headers.get("Link")
        assert 'rel="next"' in link

    def test_jobs_list_link_header_has_prev_when_offset_gt_zero(self, client_with_store):
        client, store = client_with_store
        _seed_jobs(store, 10)
        r = client.get("/jobs?limit=3&offset=3")
        link = r.headers.get("link") or r.headers.get("Link") or ""
        assert 'rel="prev"' in link


# ---------------------------------------------------------------------------
# GET /artifacts/{job_id}
# ---------------------------------------------------------------------------

class TestArtifactsPagination:

    def test_artifacts_list_paginated(self, client_with_store, tmp_path, monkeypatch):
        client, store = client_with_store
        from datasphere.api.artifact_store import LocalArtifactStore
        import datasphere.api.app as app_mod

        art_store = LocalArtifactStore(str(tmp_path))
        monkeypatch.setattr(app_mod, "artifact_store", art_store)

        files = {f"file_{i:02d}.txt": f"content {i}" for i in range(10)}
        art_store.save_files("job-art-1", files)

        r = client.get("/artifacts/job-art-1?limit=3")
        assert r.status_code == 200
        body = r.json()
        assert len(body["files"]) <= 3
        assert body["total"] == 10
        assert body["limit"] == 3
        assert body["has_more"] is True

    def test_artifacts_list_offset(self, client_with_store, tmp_path, monkeypatch):
        client, store = client_with_store
        from datasphere.api.artifact_store import LocalArtifactStore
        import datasphere.api.app as app_mod

        art_store = LocalArtifactStore(str(tmp_path))
        monkeypatch.setattr(app_mod, "artifact_store", art_store)

        files = {f"file_{i:02d}.txt": f"content {i}" for i in range(5)}
        art_store.save_files("job-art-2", files)

        r_all = client.get("/artifacts/job-art-2").json()
        r_offset = client.get("/artifacts/job-art-2?offset=2").json()
        assert r_offset["offset"] == 2
        assert len(r_offset["files"]) == len(r_all["files"]) - 2


# ---------------------------------------------------------------------------
# job_store unit tests
# ---------------------------------------------------------------------------

class TestJobStoreListAll:

    def test_job_store_list_all_with_status_filter(self):
        from datasphere.api.job_store import _InMemoryStore
        store = _InMemoryStore()
        store.create("j1", status="completed")
        store.update("j1", status="completed")
        store.create("j2", status="failed")
        store.update("j2", status="failed")
        store.create("j3", status="completed")
        store.update("j3", status="completed")

        completed = store.list_all(status="completed")
        assert len(completed) == 2
        assert all(j["status"] == "completed" for j in completed)

    def test_job_store_list_all_with_limit_offset(self):
        from datasphere.api.job_store import _InMemoryStore
        store = _InMemoryStore()
        for i in range(8):
            store.create(f"j{i}", status="completed")

        page1 = store.list_all(limit=3, offset=0)
        page2 = store.list_all(limit=3, offset=3)
        page3 = store.list_all(limit=3, offset=6)

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 2
        # No overlap
        ids1 = {j["job_id"] for j in page1}
        ids2 = {j["job_id"] for j in page2}
        assert ids1.isdisjoint(ids2)
