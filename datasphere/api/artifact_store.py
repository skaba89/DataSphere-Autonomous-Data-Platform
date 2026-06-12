"""
Artifact storage backend for DataSphere API.

Backends (priority order):
1. S3 / MinIO — if DATASPHERE_S3_BUCKET is set
2. Local filesystem — DATASPHERE_ARTIFACT_DIR (default: ~/.datasphere/artifacts)
"""
from __future__ import annotations
import io
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Iterator

_log = logging.getLogger(__name__)


class LocalArtifactStore:
    """Store artifacts on local filesystem under base_dir/{job_id}/."""

    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def save_files(self, job_id: str, files: dict[str, str]) -> list[str]:
        """Save a dict of {filename: content} strings. Returns list of saved paths."""
        job_dir = self._base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for filename, content in files.items():
            path = job_dir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            saved.append(str(path.relative_to(self._base)))
        return saved

    def get_file(self, job_id: str, filename: str) -> str | None:
        """Get a single file's content. Returns None if not found."""
        path = self._base / job_id / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_files(self, job_id: str) -> list[str]:
        """List all files for a job."""
        job_dir = self._base / job_id
        if not job_dir.exists():
            return []
        return [str(p.relative_to(job_dir)) for p in job_dir.rglob("*") if p.is_file()]

    def get_zip(self, job_id: str) -> bytes | None:
        """Build a ZIP of all artifacts for a job."""
        files = self.list_files(job_id)
        if not files:
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in files:
                content = self.get_file(job_id, filename)
                if content:
                    zf.writestr(filename, content)
        return buf.getvalue()

    def delete(self, job_id: str) -> bool:
        job_dir = self._base / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
            return True
        return False

    def exists(self, job_id: str) -> bool:
        return (self._base / job_id).exists()


class S3ArtifactStore:
    """Store artifacts in S3 or MinIO."""

    def __init__(self, bucket: str, prefix: str = "datasphere/", endpoint_url: str = ""):
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 required: pip install boto3")
        kwargs = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._s3 = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._prefix = prefix

    def _key(self, job_id: str, filename: str) -> str:
        return f"{self._prefix}{job_id}/{filename}"

    def save_files(self, job_id: str, files: dict[str, str]) -> list[str]:
        saved = []
        for filename, content in files.items():
            key = self._key(job_id, filename)
            self._s3.put_object(Bucket=self._bucket, Key=key, Body=content.encode())
            saved.append(key)
        return saved

    def get_file(self, job_id: str, filename: str) -> str | None:
        try:
            obj = self._s3.get_object(Bucket=self._bucket, Key=self._key(job_id, filename))
            return obj["Body"].read().decode()
        except Exception:
            return None

    def list_files(self, job_id: str) -> list[str]:
        prefix = f"{self._prefix}{job_id}/"
        resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        return [
            obj["Key"][len(prefix):]
            for obj in resp.get("Contents", [])
        ]

    def get_zip(self, job_id: str) -> bytes | None:
        files = self.list_files(job_id)
        if not files:
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in files:
                content = self.get_file(job_id, filename)
                if content:
                    zf.writestr(filename, content)
        return buf.getvalue()

    def delete(self, job_id: str) -> bool:
        files = self.list_files(job_id)
        if not files:
            return False
        self._s3.delete_objects(
            Bucket=self._bucket,
            Delete={"Objects": [{"Key": self._key(job_id, f)} for f in files]},
        )
        return True

    def exists(self, job_id: str) -> bool:
        return bool(self.list_files(job_id))


def _build_artifact_store():
    bucket = os.environ.get("DATASPHERE_S3_BUCKET", "")
    if bucket:
        try:
            endpoint = os.environ.get("DATASPHERE_S3_ENDPOINT", "")
            prefix = os.environ.get("DATASPHERE_S3_PREFIX", "datasphere/")
            store = S3ArtifactStore(bucket, prefix, endpoint)
            _log.info("artifact_store_backend=s3 bucket=%s", bucket)
            return store
        except Exception as exc:
            _log.warning("s3_artifact_store_failed fallback=local error=%s", exc)

    base_dir = os.environ.get(
        "DATASPHERE_ARTIFACT_DIR",
        str(Path.home() / ".datasphere" / "artifacts"),
    )
    store = LocalArtifactStore(base_dir)
    _log.info("artifact_store_backend=local path=%s", base_dir)
    return store


artifact_store = _build_artifact_store()
