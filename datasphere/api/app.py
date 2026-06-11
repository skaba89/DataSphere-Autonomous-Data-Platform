"""API REST FastAPI — expose DataSphere en tant que service HTTP."""
from __future__ import annotations
import asyncio
import io
import json
import os
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

import datasphere.adapters  # noqa: F401 — trigger adapter registry population
from datasphere.models.request import ArchitectureConstraints, BusinessRequest
from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.agents.mode_router import run_explicit, run_recommended
from datasphere.agents.proposer import generate_proposals
from datasphere.generators.dbt_project import DbtProjectGenerator
from datasphere.generators.airflow_dag import AirflowDagGenerator
from datasphere.generators.dagster_job import DagsterJobGenerator
from datasphere.generators.prefect_flow import PrefectFlowGenerator
from datasphere.api.job_store import job_store
from datasphere.api.auth import require_auth, auth_status
from datasphere.api.sse import make_sse_response
from datasphere.api.logging_config import setup_logging, get_logger, set_request_id

setup_logging()
_log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# CORS — configurable via env var (comma-separated origins or "*")
# ---------------------------------------------------------------------------
_CORS_ORIGINS_ENV = os.environ.get("DATASPHERE_CORS_ORIGINS", "")
_CORS_ORIGINS: list[str] = (
    [o.strip() for o in _CORS_ORIGINS_ENV.split(",") if o.strip()]
    if _CORS_ORIGINS_ENV
    else ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]
)

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (per IP, configurable via env)
# ---------------------------------------------------------------------------
_RATE_LIMIT_RPM = int(os.environ.get("DATASPHERE_RATE_LIMIT_RPM", "60"))

import collections
import threading

class _RateLimiter:
    """Token-bucket per IP, thread-safe."""
    def __init__(self, rpm: int):
        self._rpm = rpm
        self._windows: dict[str, list[float]] = collections.defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        if self._rpm <= 0:
            return True
        now = time.monotonic()
        window = 60.0
        with self._lock:
            timestamps = self._windows[ip]
            self._windows[ip] = [t for t in timestamps if now - t < window]
            if len(self._windows[ip]) >= self._rpm:
                return False
            self._windows[ip].append(now)
            return True

_rate_limiter = _RateLimiter(_RATE_LIMIT_RPM)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    mode: Literal["explicit", "recommended"] = Field("explicit", description="Mode de génération")
    # Mode 1 — explicit
    business_request: Optional[str] = Field(None, max_length=2000)
    cloud_provider: Optional[str] = None
    data_warehouse: Optional[str] = None
    orchestrator: Optional[str] = None
    ingestion: Optional[str] = None
    transformation: Optional[str] = None
    bi_tool: Optional[str] = None
    deployment: Optional[str] = None
    data_lake: Optional[str] = None
    catalog: Optional[str] = None
    quality: Optional[str] = None
    security: list[str] = []
    budget: Optional[str] = "medium"
    data_volume: Optional[str] = "medium"
    processing_mode: Optional[str] = "batch"
    region: Optional[str] = None
    # Mode 2 — recommended only
    security_level: Optional[str] = "rbac"
    team_size: Optional[str] = "medium"
    cloud_preference: Optional[str] = "none"
    deployment_preference: Optional[str] = None
    must_be_open_source: bool = False
    existing_tools: list[str] = []
    compliance_requirements: list[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str = ""


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[dict] = None
    error: str = ""


class ProposalsRequest(BaseModel):
    cloud_provider: str = "aws"
    budget: str = "medium"
    data_volume: str = "medium"
    processing_mode: str = "batch"
    deployment: str = "kubernetes"
    security: list[str] = ["RBAC"]


class DbtGenerateRequest(BaseModel):
    business_request: str = Field(..., min_length=3, max_length=2000)
    cloud_provider: str = "aws"
    data_warehouse: str = "snowflake"
    orchestrator: str = "airflow"
    ingestion: str = "airbyte"
    transformation: str = "dbt"
    bi_tool: str = "superset"
    deployment: str = "kubernetes"
    security: list[str] = ["RBAC"]
    budget: str = "medium"


class DagGenerateRequest(BaseModel):
    business_request: str = Field(..., min_length=3, max_length=2000)
    cloud_provider: str = "aws"
    data_warehouse: str = "snowflake"
    orchestrator: str = "airflow"
    ingestion: str = "airbyte"
    transformation: str = "dbt"
    bi_tool: str = "superset"
    deployment: str = "kubernetes"
    quality: Optional[str] = "great-expectations"
    security: list[str] = ["RBAC"]
    budget: str = "medium"
    processing_mode: str = "batch"


class LineageRequest(BaseModel):
    stack: dict
    business_request: str = ""


class CostEstimateRequest(BaseModel):
    stack: dict  # validated_stack dict
    budget: str = "medium"


class StackDiffRequest(BaseModel):
    from_stack: dict
    to_stack: dict


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

def _run_generation(job_id: str, req: GenerateRequest) -> None:
    set_request_id(job_id)
    _log.info("generation_started", extra={"job_id": job_id, "mode": req.mode})
    job_store.update(job_id, status="running")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            if req.mode == "explicit":
                stack = ExplicitStack(
                    business_request=req.business_request or "DataSphere pipeline",
                    cloud_provider=req.cloud_provider or "aws",
                    data_warehouse=req.data_warehouse or "snowflake",
                    orchestrator=req.orchestrator or "airflow",
                    ingestion=req.ingestion or "airbyte",
                    transformation=req.transformation or "dbt",
                    bi_tool=req.bi_tool or "superset",
                    deployment=req.deployment or "kubernetes",
                    data_lake=req.data_lake,
                    catalog=req.catalog,
                    quality=req.quality,
                    security=req.security,
                    budget=req.budget or "medium",
                    data_volume=req.data_volume or "medium",
                    processing_mode=req.processing_mode or "batch",
                    region=req.region,
                )
                result = run_explicit(stack, output_dir=tmp, verbose=False)
            else:
                ctx = RecommendationContext(
                    business_request=req.business_request or "DataSphere pipeline",
                    budget=req.budget or "medium",
                    data_volume=req.data_volume or "medium",
                    security_level=req.security_level or "rbac",
                    team_size=req.team_size or "medium",
                    processing_mode=req.processing_mode or "batch",
                    cloud_preference=req.cloud_preference or "none",
                    deployment_preference=req.deployment_preference,
                    must_be_open_source=req.must_be_open_source,
                    existing_tools=req.existing_tools,
                    compliance_requirements=req.compliance_requirements,
                )
                result = run_recommended(ctx, output_dir=tmp, verbose=False)

            serialized = _serialize_result(result)
            job_store.update(job_id, status="completed", result=serialized)
            _log.info("generation_completed", extra={"job_id": job_id, "success": result.success})
    except Exception as exc:
        _log.exception("generation_failed", extra={"job_id": job_id, "error": str(exc)})
        job_store.update(job_id, status="failed", error=str(exc))


def _serialize_result(result: Any) -> dict:
    out: dict[str, Any] = {
        "success": result.success,
        "errors":  result.errors,
        "request_summary": getattr(result, "request_summary", ""),
        "artifacts_path": getattr(result, "artifacts_path", ""),
    }
    for agent in ("stack_advisor", "cloud_architect", "infrastructure",
                  "cost_optimization", "security_compliance", "deployment"):
        agent_out = getattr(result, agent, None)
        if agent_out is None:
            continue
        agent_data: dict[str, Any] = {
            "success":  agent_out.success,
            "warnings": agent_out.warnings,
            "errors":   agent_out.errors,
        }
        if hasattr(agent_out, "validated_stack"):
            agent_data["validated_stack"] = agent_out.validated_stack
        if hasattr(agent_out, "total_monthly_usd"):
            agent_data["total_monthly_usd"] = agent_out.total_monthly_usd
            agent_data["total_yearly_usd"]  = agent_out.total_yearly_usd
            agent_data["optimizations"]     = agent_out.optimizations
        if hasattr(agent_out, "compliance_notes"):
            agent_data["compliance_notes"] = agent_out.compliance_notes
            agent_data["rls_policies"]     = agent_out.rls_policies
        if hasattr(agent_out, "pipeline_stages"):
            agent_data["pipeline_stages"] = agent_out.pipeline_stages
        if hasattr(agent_out, "provider"):
            agent_data["provider"] = agent_out.provider
            agent_data["region"]   = agent_out.region
        agent_data["artifact_keys"] = list(agent_out.artifacts.keys()) if agent_out.artifacts else []
        out[agent] = agent_data
    return out


def _build_stack_report(result: dict) -> str:
    """Generate a markdown summary report from a serialized job result."""
    lines: list[str] = ["# DataSphere — Stack Report\n"]

    sa = result.get("stack_advisor") or {}
    stack = sa.get("validated_stack") or {}
    if stack:
        lines.append("## Architecture Summary\n")
        lines.append("| Layer | Tool |")
        lines.append("|-------|------|")
        for layer, tool in stack.items():
            lines.append(f"| {layer} | {tool} |")
        lines.append("")

    co = result.get("cost_optimization") or {}
    if co.get("total_monthly_usd") is not None:
        lines.append("## Cost Estimation\n")
        lines.append(f"- Monthly: **${co['total_monthly_usd']:,.0f}**")
        if co.get("total_yearly_usd") is not None:
            lines.append(f"- Yearly:  **${co['total_yearly_usd']:,.0f}**")
        optimizations = co.get("optimizations") or []
        if optimizations:
            lines.append("\n### Optimizations")
            for opt in optimizations:
                lines.append(f"- {opt}")
        lines.append("")

    sec = result.get("security_compliance") or {}
    compliance_notes = sec.get("compliance_notes") or []
    if compliance_notes:
        lines.append("## Compliance Notes\n")
        for note in compliance_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Generated Artifact Keys\n")
    for agent_name in ("stack_advisor", "cloud_architect", "infrastructure",
                       "cost_optimization", "security_compliance", "deployment"):
        agent = result.get(agent_name) or {}
        keys = agent.get("artifact_keys") or []
        if keys:
            lines.append(f"### {agent_name}")
            for k in keys:
                lines.append(f"- {k}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    _log.info("datasphere_api_starting", extra={"version": _VERSION})
    # Startup: verify job store is reachable
    try:
        job_store.list_all()
        _log.info("job_store_ok")
    except Exception as exc:
        _log.error("job_store_unavailable", extra={"error": str(exc)})
    yield
    # Shutdown
    _log.info("datasphere_api_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DataSphere API",
        description=(
            "API REST pour la génération automatique d'architectures data.\n\n"
            "**Mode 1** — Stack explicite : vous choisissez chaque outil.\n\n"
            "**Mode 2** — Stack recommandée : vous donnez budget/volume/équipe, "
            "les agents recommandent."
        ),
        version=_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    # ------------------------------------------------------------------
    # CORS — restrict to configured origins (default: localhost only)
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # ------------------------------------------------------------------
    # Request ID + Rate limiting middleware
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def _request_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(req_id)

        # Rate limiting on mutation endpoints
        if request.method in ("POST", "PUT", "DELETE"):
            ip = request.client.host if request.client else "unknown"
            if not _rate_limiter.is_allowed(ip):
                _log.warning("rate_limit_exceeded", extra={"ip": ip, "path": request.url.path})
                return Response(
                    content='{"detail":"Too many requests — rate limit exceeded"}',
                    status_code=429,
                    headers={"Content-Type": "application/json", "Retry-After": "60"},
                )

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        _log.info(
            "http_request",
            extra={
                "method": request.method,
                "path":   request.url.path,
                "status": response.status_code,
                "ms":     duration_ms,
            },
        )
        return response

    # ------------------------------------------------------------------
    # Web UI
    # ------------------------------------------------------------------

    @app.get("/ui", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
    @app.get("/ui/", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
    def web_ui() -> HTMLResponse:
        """Interface web DataSphere."""
        html_file = _TEMPLATE_DIR / "index.html"
        if not html_file.exists():
            return HTMLResponse("<h1>UI not found</h1>", status_code=404)
        return HTMLResponse(html_file.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health", tags=["system"])
    @app.get("/healthz", tags=["system"])
    def health() -> dict:
        """Liveness probe — always returns 200 if the process is alive."""
        return {"status": "ok", "version": _VERSION, "timestamp": time.time(), **auth_status()}

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict:
        """Readiness probe — returns 503 if dependencies are unavailable."""
        checks: dict[str, str] = {}
        ok = True

        # Check job store
        try:
            job_store.list_all()
            checks["job_store"] = "ok"
        except Exception as exc:
            checks["job_store"] = f"error: {exc}"
            ok = False

        # Check temp dir writable
        try:
            with tempfile.NamedTemporaryFile(prefix="datasphere_ready_", delete=True):
                pass
            checks["tmp_dir"] = "ok"
        except Exception as exc:
            checks["tmp_dir"] = f"error: {exc}"
            ok = False

        status_code = 200 if ok else 503
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content={"status": "ready" if ok else "not_ready", "checks": checks, "version": _VERSION},
            status_code=status_code,
        )

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": "DataSphere Autonomous Data Platform",
            "version": _VERSION,
            "ui":   "/ui",
            "docs": "/docs",
            "health": "/health",
            "endpoints": [
                "GET  /ui  → Interface web",
                "POST /generate",
                "GET  /generate/stream?job_id=<id>",
                "GET  /healthz  /readyz",
                "GET  /jobs/{job_id}",
                "POST /proposals",
                "POST /dbt/generate",
                "POST /dags/airflow/generate",
                "POST /dagster/generate",
                "POST /prefect/generate",
                "POST /terraform/generate",
                "GET  /stacks/supported",
            ],
        }

    # ------------------------------------------------------------------
    # Async generation
    # ------------------------------------------------------------------

    @app.get("/generate/stream", tags=["generation"])
    async def stream_generate(job_id: str = Query(..., description="Job ID from POST /generate")) -> StreamingResponse:
        """
        Streaming SSE endpoint — yields progress events for an existing job.

        Connect with `EventSource('/generate/stream?job_id=<id>')`.
        Events: `status`, `log`, `done`, `error`.
        """
        if not job_store.get(job_id):
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return make_sse_response(job_id)

    @app.post("/generate", response_model=JobResponse, tags=["generation"])
    async def generate(
        req: GenerateRequest,
        background_tasks: BackgroundTasks,
        _: None = Depends(require_auth),
    ) -> JobResponse:
        """
        Lance la génération asynchrone d'une architecture data complète.

        Retourne un `job_id` à interroger via `GET /jobs/{job_id}`.
        """
        if not req.business_request:
            raise HTTPException(status_code=422, detail="business_request est requis")

        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="pending")
        _log.info("job_enqueued", extra={"job_id": job_id, "mode": req.mode})
        background_tasks.add_task(_run_generation, job_id, req)
        return JobResponse(
            job_id=job_id,
            status="pending",
            message=f"Génération lancée. Interrogez GET /jobs/{job_id}",
        )

    @app.post("/generate/sync", tags=["generation"])
    async def generate_sync(req: GenerateRequest, _: None = Depends(require_auth)) -> dict:
        """
        Génération synchrone — exécutée dans un thread pool pour ne pas bloquer l'event loop.
        Recommandé pour les tests et les petites architectures.
        """
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

    # ------------------------------------------------------------------
    # Job status
    # ------------------------------------------------------------------

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["generation"])
    def get_job(job_id: str) -> JobStatusResponse:
        """Récupère le statut et le résultat d'un job de génération."""
        job = job_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
        return JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            result=job.get("result"),
            error=job.get("error", ""),
        )

    @app.get("/jobs", tags=["generation"])
    def list_jobs() -> list[dict]:
        """Liste tous les jobs (persistés dans SQLite)."""
        return job_store.list_all()

    @app.delete("/jobs/{job_id}", tags=["generation"])
    def delete_job(job_id: str) -> dict:
        """Supprime un job de l'historique."""
        if not job_store.get(job_id):
            raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
        job_store.delete(job_id)
        return {"deleted": job_id}

    @app.get("/jobs/{job_id}/download", tags=["generation"])
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

    @app.post("/jobs/purge", tags=["generation"])
    def purge_jobs(max_age_hours: int = 24) -> dict:
        """Supprime les jobs plus vieux que max_age_hours."""
        deleted = job_store.purge_old(max_age_hours * 3600)
        return {"deleted_count": deleted}

    # ------------------------------------------------------------------
    # Proposals (Mode 2)
    # ------------------------------------------------------------------

    @app.post("/proposals", tags=["recommendations"])
    def get_proposals(req: ProposalsRequest) -> dict:
        """
        Génère 2-3 propositions d'architecture selon les contraintes fournies.
        """
        raw = {
            "cloud_provider":  req.cloud_provider,
            "budget":          req.budget,
            "data_volume":     req.data_volume,
            "processing_mode": req.processing_mode,
            "deployment":      req.deployment,
            "security":        req.security,
            "iac":             "helm" if req.deployment == "kubernetes" else "docker-compose",
            "region":          None,
            "data_warehouse":  "auto",
            "orchestrator":    "auto",
            "ingestion":       "auto",
            "transformation":  "auto",
            "data_lake":       "auto",
            "bi_tool":         "auto",
            "catalog":         "auto",
            "quality":         "auto",
        }
        proposals = generate_proposals(raw)
        return {
            "count": len(proposals),
            "proposals": [
                {
                    "id":                   p.id,
                    "name":                 p.name,
                    "tagline":              p.tagline,
                    "complexity":           p.complexity,
                    "estimated_monthly_usd": p.estimated_monthly_usd,
                    "time_to_deploy":       p.time_to_deploy,
                    "pros":                 p.pros,
                    "cons":                 p.cons,
                    "stack": {
                        "cloud":          p.constraints.cloud_provider,
                        "warehouse":      p.constraints.data_warehouse,
                        "orchestrator":   p.constraints.orchestrator,
                        "ingestion":      p.constraints.ingestion,
                        "transformation": p.constraints.transformation,
                        "data_lake":      p.constraints.data_lake,
                        "bi_tool":        p.constraints.bi_tool,
                    },
                }
                for p in proposals
            ],
        }

    # ------------------------------------------------------------------
    # dbt project generation
    # ------------------------------------------------------------------

    @app.post("/dbt/generate", tags=["generators"])
    def generate_dbt_project(req: DbtGenerateRequest) -> dict:
        """
        Génère un scaffold dbt complet (dbt_project.yml, profiles.yml, modèles, tests).
        Retourne le contenu de chaque fichier.
        """
        constraints = ArchitectureConstraints(
            cloud_provider=req.cloud_provider,
            data_warehouse=req.data_warehouse,
            orchestrator=req.orchestrator,
            ingestion=req.ingestion,
            transformation=req.transformation,
            bi_tool=req.bi_tool,
            deployment=req.deployment,
            security=req.security,
            budget=req.budget,
            data_lake=None,
            catalog=None,
            quality=None,
        )
        gen = DbtProjectGenerator()
        project = gen.generate(req.business_request, constraints)
        return {
            "project_name": gen._project_name(req.business_request),
            "warehouse":    req.data_warehouse,
            "file_count":   len(project.files),
            "files":        project.files,
        }

    # ------------------------------------------------------------------
    # Airflow DAG generation
    # ------------------------------------------------------------------

    @app.post("/dags/airflow/generate", tags=["generators"])
    def generate_airflow_dags(req: DagGenerateRequest) -> dict:
        """
        Génère les DAGs Airflow Python pour le pipeline et les quality checks.
        """
        constraints = ArchitectureConstraints(
            cloud_provider=req.cloud_provider,
            data_warehouse=req.data_warehouse,
            orchestrator=req.orchestrator,
            ingestion=req.ingestion,
            transformation=req.transformation,
            bi_tool=req.bi_tool,
            deployment=req.deployment,
            security=req.security,
            budget=req.budget,
            data_lake=None,
            catalog=None,
            quality=req.quality,
            processing_mode=req.processing_mode,
        )
        gen = AirflowDagGenerator()
        dags = gen.generate(req.business_request, constraints)
        return {
            "dag_count": len([k for k in dags.files if k.endswith(".py")]),
            "files":     dags.files,
        }

    # ------------------------------------------------------------------
    # Dagster project generation
    # ------------------------------------------------------------------

    @app.post("/dagster/generate", tags=["generators"])
    def generate_dagster_project(req: DbtGenerateRequest) -> dict:
        """Génère un projet Dagster complet avec SDA, jobs, schedules et sensors."""
        constraints = ArchitectureConstraints(
            cloud_provider=req.cloud_provider,
            data_warehouse=req.data_warehouse,
            orchestrator="dagster",
            ingestion=req.ingestion,
            transformation=req.transformation,
            bi_tool=req.bi_tool,
            deployment=req.deployment,
            security=req.security,
            budget=req.budget,
            data_lake=None,
            catalog=None,
            quality=None,
        )
        gen = DagsterJobGenerator()
        project = gen.generate(req.business_request, constraints)
        return {
            "project_name": gen._slug(req.business_request),
            "warehouse":    req.data_warehouse,
            "file_count":   len(project.files),
            "files":        project.files,
        }

    # ------------------------------------------------------------------
    # Prefect flow generation
    # ------------------------------------------------------------------

    @app.post("/prefect/generate", tags=["generators"])
    def generate_prefect_flows(req: DbtGenerateRequest) -> dict:
        """Génère des flows Prefect avec tasks, deployments et blocks."""
        constraints = ArchitectureConstraints(
            cloud_provider=req.cloud_provider,
            data_warehouse=req.data_warehouse,
            orchestrator="prefect",
            ingestion=req.ingestion,
            transformation=req.transformation,
            bi_tool=req.bi_tool,
            deployment=req.deployment,
            security=req.security,
            budget=req.budget,
            data_lake=None,
            catalog=None,
            quality=None,
        )
        gen = PrefectFlowGenerator()
        flows = gen.generate(req.business_request, constraints)
        return {
            "project_name": gen._slug(req.business_request),
            "warehouse":    req.data_warehouse,
            "file_count":   len(flows.files),
            "files":        flows.files,
        }

    # ------------------------------------------------------------------
    # Terraform / IaC generation
    # ------------------------------------------------------------------

    @app.post("/terraform/generate", tags=["generators"])
    def generate_terraform(req: DagGenerateRequest) -> dict:
        """Génère un projet Terraform complet (providers, modules networking/warehouse/k8s/IAM)."""
        try:
            from datasphere.generators.terraform import TerraformGenerator
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=f"TerraformGenerator not available: {exc}")
        constraints = ArchitectureConstraints(
            cloud_provider=req.cloud_provider,
            data_warehouse=req.data_warehouse,
            orchestrator=req.orchestrator,
            ingestion=req.ingestion,
            transformation=req.transformation,
            bi_tool=req.bi_tool,
            deployment=req.deployment,
            security=req.security,
            budget=req.budget,
            data_lake=None,
            catalog=None,
            quality=req.quality,
            processing_mode=req.processing_mode,
        )
        gen = TerraformGenerator()
        project = gen.generate(req.business_request, constraints)
        return {
            "provider":   req.cloud_provider,
            "warehouse":  req.data_warehouse,
            "file_count": len(project.files),
            "files":      project.files,
        }

    # ------------------------------------------------------------------
    # Lineage diagram generation
    # ------------------------------------------------------------------

    @app.post("/lineage/generate", tags=["generators"])
    def generate_lineage(req: LineageRequest) -> dict:
        """Génère un diagramme de lineage Mermaid depuis une stack validée."""
        from datasphere.generators.lineage import LineageGenerator
        gen = LineageGenerator()
        output = gen.generate(req.stack, req.business_request)
        embed_url = LineageGenerator.embed_url(output.mermaid)
        return {
            "mermaid": output.mermaid,
            "nodes": output.nodes,
            "edge_count": len(output.edges),
            "embed_url": embed_url,
        }

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    @app.post("/costs/estimate", tags=["analysis"])
    def estimate_cost(req: CostEstimateRequest) -> dict:
        """Estimate detailed cost breakdown for a stack with multi-cloud comparison."""
        from datasphere.agents.cost_tables import CostCalculator
        calculator = CostCalculator()
        breakdown = calculator.calculate(req.stack, req.budget)
        return {
            "total_monthly_usd": breakdown.total_monthly_usd,
            "total_yearly_usd":  breakdown.total_yearly_usd,
            "budget_tier":       breakdown.budget_tier,
            "line_items": [
                {
                    "component":   item.component,
                    "tool":        item.tool,
                    "monthly_usd": item.monthly_usd,
                    "yearly_usd":  item.yearly_usd,
                    "notes":       item.notes,
                }
                for item in breakdown.line_items
            ],
            "savings_tips": breakdown.savings_tips,
            "comparison":   breakdown.comparison,
        }

    # ------------------------------------------------------------------
    # Stack diff & migration plan
    # ------------------------------------------------------------------

    @app.post("/stacks/diff", tags=["analysis"])
    def stack_diff(req: StackDiffRequest) -> dict:
        """Compare two stacks and generate a migration plan."""
        from datasphere.generators.stack_diff import StackDiffGenerator
        gen = StackDiffGenerator()
        plan = gen.diff(req.from_stack, req.to_stack)
        return {
            "summary": plan.summary,
            "total_estimated_days": plan.total_estimated_days,
            "overall_risk": plan.overall_risk,
            "migration_order": plan.migration_order,
            "rollback_strategy": plan.rollback_strategy,
            "changes": [
                {
                    "component": c.component,
                    "from_tool": c.from_tool,
                    "to_tool": c.to_tool,
                    "change_type": c.change_type,
                    "effort": c.effort,
                    "risk": c.risk,
                    "estimated_days": c.estimated_days,
                    "migration_steps": c.migration_steps,
                }
                for c in plan.changes
            ],
        }

    # ------------------------------------------------------------------
    # Supported stacks catalog
    # ------------------------------------------------------------------

    @app.get("/stacks/supported", tags=["catalog"])
    def supported_stacks() -> dict:
        """Retourne tous les outils supportés par catégorie."""
        from datasphere.core.config import ALLOWED
        return {"categories": ALLOWED}

    @app.get("/stacks/adapters", tags=["catalog"])
    def list_adapters() -> dict:
        """Retourne tous les adaptateurs enregistrés dans le registry."""
        from datasphere.core.registry import registry
        adapters: dict[str, list[str]] = {}
        for (category, name) in registry._registry:
            adapters.setdefault(category, []).append(name)
        return {"adapter_count": len(registry._registry), "adapters": adapters}

    return app


# ---------------------------------------------------------------------------
# Entry point (uvicorn datasphere.api.app:app)
# ---------------------------------------------------------------------------

app = create_app()
