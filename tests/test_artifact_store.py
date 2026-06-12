"""Tests for artifact storage backend and API endpoints."""
from __future__ import annotations
import io
import zipfile
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# LocalArtifactStore unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def local_store(tmp_path):
    from datasphere.api.artifact_store import LocalArtifactStore
    return LocalArtifactStore(str(tmp_path / "artifacts"))


def test_local_store_save_and_get(local_store):
    local_store.save_files("job1", {"main.tf": "resource \"aws_s3_bucket\" {}"})
    content = local_store.get_file("job1", "main.tf")
    assert content == "resource \"aws_s3_bucket\" {}"


def test_local_store_list_files(local_store):
    local_store.save_files("job2", {"a.tf": "a", "b.yml": "b"})
    files = local_store.list_files("job2")
    assert sorted(files) == ["a.tf", "b.yml"]


def test_local_store_get_zip_returns_bytes(local_store):
    local_store.save_files("job3", {"dag.py": "from airflow import DAG"})
    result = local_store.get_zip("job3")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_local_store_zip_contains_all_files(local_store):
    files = {"main.tf": "terraform {}", "variables.tf": "variable x {}"}
    local_store.save_files("job4", files)
    zip_bytes = local_store.get_zip("job4")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert names == {"main.tf", "variables.tf"}


def test_local_store_delete(local_store):
    local_store.save_files("job5", {"file.tf": "content"})
    assert local_store.exists("job5")
    result = local_store.delete("job5")
    assert result is True
    assert not local_store.exists("job5")


def test_local_store_exists(local_store):
    assert not local_store.exists("nonexistent")
    local_store.save_files("job6", {"x.py": "pass"})
    assert local_store.exists("job6")


def test_local_store_get_nonexistent_returns_none(local_store):
    result = local_store.get_file("nosuchjob", "nosuchfile.tf")
    assert result is None


def test_local_store_nested_filename(local_store):
    local_store.save_files("job7", {"subdir/file.tf": "# nested"})
    content = local_store.get_file("job7", "subdir/file.tf")
    assert content == "# nested"
    files = local_store.list_files("job7")
    assert "subdir/file.tf" in files


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture
def patched_client(tmp_path, monkeypatch):
    """TestClient with artifact_store pointing to a temp directory."""
    from datasphere.api.artifact_store import LocalArtifactStore
    store = LocalArtifactStore(str(tmp_path / "test_artifacts"))

    import datasphere.api.app as app_mod
    monkeypatch.setattr(app_mod, "artifact_store", store)

    # Also patch in artifact_store module so the app picks up the same instance
    import datasphere.api.artifact_store as as_mod
    monkeypatch.setattr(as_mod, "artifact_store", store)

    from fastapi.testclient import TestClient
    return TestClient(app_mod.app), store


def test_api_list_artifacts_empty(patched_client):
    client, store = patched_client
    resp = client.get("/artifacts/unknown-job-id")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("count", data.get("total", 0)) == 0
    assert data["files"] == []


def test_api_list_artifacts_with_files(patched_client):
    client, store = patched_client
    store.save_files("myjob", {"infrastructure/main.tf": "terraform {}", "deployment/helm.yml": "chart: x"})
    resp = client.get("/artifacts/myjob")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("count", data.get("total", 0)) == 2
    assert "infrastructure/main.tf" in data["files"]


def test_api_get_artifact_content(patched_client):
    client, store = patched_client
    store.save_files("job-abc", {"infrastructure/main.tf": "terraform {}"})
    resp = client.get("/artifacts/job-abc/infrastructure/main.tf")
    assert resp.status_code == 200
    assert "terraform" in resp.text


def test_api_get_artifact_not_found_404(patched_client):
    client, _ = patched_client
    resp = client.get("/artifacts/no-such-job/no-such-file.tf")
    assert resp.status_code == 404


def test_api_download_artifacts_zip(patched_client):
    client, store = patched_client
    store.save_files("zipjob", {"main.tf": "terraform {}", "dag.py": "from airflow import DAG"})
    resp = client.get("/artifacts/zipjob/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
    assert "main.tf" in names
    assert "dag.py" in names


def test_api_download_artifacts_zip_not_found(patched_client):
    client, _ = patched_client
    resp = client.get("/artifacts/empty-job/download")
    assert resp.status_code == 404


def test_readyz_includes_artifact_store_check(patched_client):
    client, _ = patched_client
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "artifact_store" in data["checks"]
    assert data["checks"]["artifact_store"] == "ok"
