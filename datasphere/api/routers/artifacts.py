"""Artifact storage routes: /artifacts/{job_id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from datasphere.api.artifact_store import artifact_store

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{job_id}/download", tags=["artifacts"])
def download_artifacts_zip(job_id: str) -> Response:
    """Download all artifacts for a job as a ZIP archive."""
    zip_bytes = artifact_store.get_zip(job_id)
    if zip_bytes is None:
        raise HTTPException(status_code=404, detail="No artifacts found for this job")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="artifacts-{job_id[:8]}.zip"'},
    )


@router.get("/artifacts/{job_id}", tags=["artifacts"])
def list_artifacts(job_id: str) -> dict:
    """List all stored artifacts for a job."""
    files = artifact_store.list_files(job_id)
    return {"job_id": job_id, "files": files, "count": len(files)}


@router.get("/artifacts/{job_id}/{filename:path}", tags=["artifacts"])
def get_artifact(job_id: str, filename: str) -> Response:
    """Download a single artifact file."""
    content = artifact_store.get_file(job_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Artifact {filename} not found")
    media_type = "text/plain"
    if filename.endswith(".json"):
        media_type = "application/json"
    elif filename.endswith((".yml", ".yaml")):
        media_type = "text/yaml"
    elif filename.endswith(".tf"):
        media_type = "text/plain"
    return Response(content=content, media_type=media_type)
