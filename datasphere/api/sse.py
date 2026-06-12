"""
Server-Sent Events helpers for streaming generation progress.

Usage:
    GET /generate/stream?job_id=<uuid>

The endpoint streams JSON-encoded events as the job progresses:
    data: {"type": "status", "status": "running", "step": "stack_advisor", "progress": 16}\n\n
    data: {"type": "log",    "message": "Stack validée"}\n\n
    data: {"type": "done",   "result": {...}}\n\n
    data: {"type": "error",  "error": "..."}\n\n
"""
from __future__ import annotations
import asyncio
import json
import time
from collections.abc import AsyncGenerator
from fastapi.responses import StreamingResponse

from datasphere.api.job_store import job_store
from datasphere.api.tenancy import get_tenant_id

_POLL_INTERVAL = 0.4   # seconds between store polls
_TIMEOUT       = 300   # seconds before giving up


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


STEP_LABELS = {
    "pending":  ("Initialisation", 5),
    "running":  ("En cours", 20),
    # These come from the job metadata if the generation loop sets them
    "stack_advisor":       ("Validation du stack", 16),
    "cloud_architect":     ("Architecture cloud", 32),
    "infrastructure":      ("Infrastructure", 48),
    "cost_optimization":   ("Optimisation des coûts", 64),
    "security_compliance": ("Sécurité & conformité", 80),
    "deployment":          ("Configuration déploiement", 96),
    "completed": ("Terminé", 100),
    "failed":    ("Échec", 100),
}


async def stream_job_progress(job_id: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events until job is done or timeout."""
    deadline = time.monotonic() + _TIMEOUT
    last_status: str | None = None

    while time.monotonic() < deadline:
        job = job_store.get(job_id)
        if job is None:
            yield _event({"type": "error", "error": f"Job {job_id} not found"})
            return

        status = job["status"]
        step   = job.get("meta", {}).get("step", status) if job.get("meta") else status
        label, progress = STEP_LABELS.get(step, ("En cours", 50))

        if status != last_status:
            yield _event({
                "type":      "status",
                "status":    status,
                "step":      step,
                "label":     label,
                "progress":  progress,
                "tenant_id": get_tenant_id(),
            })
            last_status = status

        if status == "completed":
            yield _event({"type": "done", "result": job.get("result", {})})
            return

        if status == "failed":
            yield _event({"type": "error", "error": job.get("error", "Unknown error")})
            return

        await asyncio.sleep(_POLL_INTERVAL)

    yield _event({"type": "error", "error": "Timeout: job did not complete in time"})


def make_sse_response(job_id: str) -> StreamingResponse:
    return StreamingResponse(
        stream_job_progress(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
