"""Generation routes: /generate, /generate/sync, /generate/stream, /jobs."""
from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from datasphere.api.auth import require_auth
from datasphere.api.job_store import job_store
from datasphere.api.metrics import metrics
from datasphere.api.sse import make_sse_response
from datasphere.api.tenancy import get_tenant_id, tenant_job_id
from datasphere.api.logging_config import get_logger
from datasphere.api.generation_utils import _run_generation, _build_stack_report
from datasphere.api.models import GenerateRequest, JobResponse, JobStatusResponse
from datasphere.api.openapi_examples import GENERATE_REQUEST_EXAMPLE, GENERATE_RESPONSE_EXAMPLE

_log = get_logger(__name__)

router = APIRouter(tags=["generation"])


@router.get("/generate/stream", tags=["generation"])
async def stream_generate(job_id: str = Query(..., description="Job ID from POST /generate")) -> StreamingResponse:
    """
    Streaming SSE endpoint — yields progress events for an existing job.

    Connect with `EventSource('/generate/stream?job_id=<id>')`.
    Events: `status`, `log`, `done`, `error`.
    """
    scoped_id = tenant_job_id(job_id)
    actual_id = scoped_id if job_store.get(scoped_id) else job_id
    if not job_store.get(actual_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return make_sse_response(actual_id)


@router.post(
    "/generate",
    response_model=JobResponse,
    tags=["generation"],
    summary="Génération asynchrone d'architecture",
    description="""
Lance la génération asynchrone d'une architecture data complète.

Retourne un `job_id` immédiatement. Interrogez l'état via:
- `GET /jobs/{job_id}` — polling
- `GET /generate/stream?job_id=<id>` — Server-Sent Events (temps réel)

**Headers optionnels:**
- `X-Tenant-ID` — isolation multi-tenant
- `X-Slack-Webhook` — notification Slack à la fin du job
- `X-Teams-Webhook` — notification Microsoft Teams
    """,
    response_description="Job créé avec son identifiant unique",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "explicit_aws_snowflake": {
                            "summary": "Stack explicite AWS + Snowflake",
                            "value": GENERATE_REQUEST_EXAMPLE,
                        },
                        "recommended_mode": {
                            "summary": "Mode recommandé",
                            "value": {
                                "mode": "recommended",
                                "business_request": "Startup analytics avec budget limité",
                                "budget": "low",
                                "data_volume": "small",
                                "team_size": "small",
                                "must_be_open_source": True,
                            },
                        },
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "example": {
                            "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "status": "pending",
                            "message": "Génération lancée. Interrogez GET /jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        }
                    }
                }
            }
        },
    },
)
async def generate(
    req: GenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_auth),
) -> JobResponse:
    """Lance la génération asynchrone d'une architecture data complète."""
    if not req.business_request:
        raise HTTPException(status_code=422, detail="business_request est requis")

    job_id = str(uuid.uuid4())
    scoped_id = tenant_job_id(job_id)
    slack_webhook = request.headers.get("X-Slack-Webhook", "")
    teams_webhook = request.headers.get("X-Teams-Webhook", "")
    meta: dict = {"tenant_id": get_tenant_id()}
    if slack_webhook:
        meta["slack_webhook"] = slack_webhook
    if teams_webhook:
        meta["teams_webhook"] = teams_webhook
    job_store.create(scoped_id, status="pending", meta=meta)
    metrics.record_job_created(mode=req.mode or "explicit")
    _log.info("job_enqueued", extra={"job_id": job_id, "scoped_id": scoped_id, "mode": req.mode, "tenant_id": get_tenant_id()})

    # ------------------------------------------------------------------
    # ARQ integration -- use Redis queue when available; fall back to
    # BackgroundTasks for single-process / development mode.
    # ------------------------------------------------------------------
    _arq_job = None
    try:
        from datasphere.api.worker import enqueue_generation as _enqueue_arq  # noqa: PLC0415
        _arq_job = await _enqueue_arq(scoped_id, req.model_dump())
    except Exception:  # pragma: no cover -- worker import failure is non-fatal
        _arq_job = None

    if _arq_job is None:
        background_tasks.add_task(_run_generation, scoped_id, req)
    else:
        _log.info("job_sent_to_arq", extra={"job_id": job_id, "scoped_id": scoped_id})

    return JobResponse(
        job_id=job_id,
        status="pending",
        message=f"Génération lancée. Interrogez GET /jobs/{job_id}",
    )


@router.post(
    "/generate/sync",
    tags=["generation"],
    summary="Génération synchrone d'architecture",
    description="""
Génère une architecture data complète de façon synchrone.

Exécutée dans un thread pool pour ne pas bloquer l'event loop.

**Modes disponibles:**
- `explicit` — vous choisissez chaque outil de la stack
- `recommended` — les agents recommandent la meilleure stack selon vos contraintes

**Agents impliqués:**
1. Stack Advisor — valide et optimise la stack
2. Cloud Architect — dimensionne l'infrastructure
3. Infrastructure Generator — génère les fichiers IaC
4. Cost Optimizer — estime les coûts avec comparaison multi-cloud
5. Security & Compliance — vérifie RBAC, SOC2, GDPR
6. Deployment Generator — génère le pipeline CI/CD

Recommandé pour les tests et les petites architectures.
Pour la production, utilisez `POST /generate` (async) + `GET /generate/stream` (SSE).
    """,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "explicit_aws_snowflake": {
                            "summary": "Stack explicite AWS + Snowflake",
                            "value": GENERATE_REQUEST_EXAMPLE,
                        },
                        "recommended_mode": {
                            "summary": "Mode recommandé (agents choisissent)",
                            "value": {
                                "mode": "recommended",
                                "business_request": "Startup analytics avec budget limité",
                                "budget": "low",
                                "data_volume": "small",
                                "team_size": "small",
                                "must_be_open_source": True,
                            },
                        },
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "example": GENERATE_RESPONSE_EXAMPLE,
                    }
                }
            }
        },
    },
)
async def generate_sync(req: GenerateRequest, _: None = Depends(require_auth)) -> dict:
    """Génération synchrone d'architecture data complète."""
    if not req.business_request:
        raise HTTPException(status_code=422, detail="business_request est requis")

    job_id = str(uuid.uuid4())
    job_store.create(job_id, status="pending")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_generation, job_id, req)
    job = job_store.get(job_id) or {}
    if job.get("status") == "failed":
        raise HTTPException(status_code=500, detail=job.get("error", "Generation failed"))
    return job.get("result", {})


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["generation"])
def get_job(job_id: str) -> JobStatusResponse:
    """Récupère le statut et le résultat d'un job de génération."""
    scoped_id = tenant_job_id(job_id)
    job = job_store.get(scoped_id) or job_store.get(job_id)  # fallback for default tenant
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error", ""),
    )


@router.get("/jobs", tags=["generation"])
def list_jobs() -> list[dict]:
    """Liste tous les jobs filtrés par tenant courant."""
    all_jobs = job_store.list_all()
    tenant = get_tenant_id()
    if tenant != "default":
        prefix = f"{tenant}:"
        return [j for j in all_jobs if j["job_id"].startswith(prefix)]
    return [j for j in all_jobs if ":" not in j["job_id"]]


@router.delete("/jobs/{job_id}", tags=["generation"])
def delete_job(job_id: str) -> dict:
    """Supprime un job de l'historique."""
    scoped_id = tenant_job_id(job_id)
    if not (job_store.get(scoped_id) or job_store.get(job_id)):
        raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
    job_store.delete(scoped_id)
    return {"deleted": job_id}


@router.get("/jobs/{job_id}/download", tags=["generation"])
def download_job(job_id: str) -> Response:
    """Télécharge les artefacts d'un job terminé sous forme de fichier ZIP."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
    if job.get("status") != "completed":
        raise HTTPException(status_code=404, detail=f"Job {job_id} n'est pas terminé")

    result = job.get("result") or {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # manifest.json
        stack_summary = {}
        sa = result.get("stack_advisor")
        if sa and isinstance(sa, dict):
            stack_summary = sa.get("validated_stack") or {}
        manifest = {
            "job_id": job_id,
            "created_at": job.get("created_at", ""),
            "stack_summary": stack_summary,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        # stack_report.md
        zf.writestr("stack_report.md", _build_stack_report(result))

        # Walk result for dicts that have a "files" key
        def _add_files(node: Any) -> None:
            if isinstance(node, dict):
                if "files" in node and isinstance(node["files"], dict):
                    for fname, content in node["files"].items():
                        zf.writestr(fname, content if isinstance(content, str) else json.dumps(content, indent=2))
                for v in node.values():
                    _add_files(v)
            elif isinstance(node, list):
                for item in node:
                    _add_files(item)

        _add_files(result)

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="datasphere-{job_id[:8]}.zip"'},
    )


@router.post("/jobs/purge", tags=["generation"])
def purge_jobs(max_age_hours: int = 24) -> dict:
    """Supprime les jobs plus vieux que max_age_hours."""
    deleted = job_store.purge_old(max_age_hours * 3600)
    return {"deleted_count": deleted}
