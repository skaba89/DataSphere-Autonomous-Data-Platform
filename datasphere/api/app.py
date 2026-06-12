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
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

import datasphere.adapters  # noqa: F401 — trigger adapter registry population
from datasphere.api.openapi_examples import (
    GENERATE_REQUEST_EXAMPLE,
    GENERATE_RESPONSE_EXAMPLE,
    DBT_REQUEST_EXAMPLE,
    TERRAFORM_REQUEST_EXAMPLE,
    LINEAGE_REQUEST_EXAMPLE,
    COST_ESTIMATE_REQUEST_EXAMPLE,
    STACK_DIFF_REQUEST_EXAMPLE,
    WEBHOOK_REQUEST_EXAMPLE,
    TEMPLATE_GENERATE_EXAMPLE,
)
from datasphere.plugins import plugin_registry
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
from datasphere.api.tracing import setup_tracing, start_span
from datasphere.api.tenancy import get_tenant_id, set_tenant_id, tenant_job_id, validate_tenant_id
from datasphere.api.webhooks import webhook_registry
from datasphere.api.artifact_store import artifact_store
from datasphere.api.metrics import metrics
from datasphere.api.notifications import notification_service

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


class WebhookRegisterRequest(BaseModel):
    url: str = Field(..., description="URL to POST to when events fire")
    events: list[str] = Field(default=["*"], description="Events: job.completed, job.failed, or *")
    secret: str = Field(default="", description="Optional HMAC signing secret")


class TemplateGenerateRequest(BaseModel):
    template_id: str
    business_request: str = Field(..., min_length=3, max_length=2000)
    overrides: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

def _run_generation(job_id: str, req: GenerateRequest) -> None:
    set_request_id(job_id)
    _log.info("generation_started", extra={"job_id": job_id, "mode": req.mode})
    job_store.update(job_id, status="running")
    job_start = time.time()
    with start_span("generation.run", {"job_id": job_id, "mode": req.mode}):
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

                # Persist generated files to artifact store
                all_files: dict[str, str] = {}
                for agent_name in ("infrastructure", "deployment"):
                    agent_out = getattr(result, agent_name, None)
                    if agent_out and agent_out.artifacts:
                        for fname, content in agent_out.artifacts.items():
                            all_files[f"{agent_name}/{fname}"] = str(content)
                if all_files:
                    try:
                        artifact_store.save_files(job_id, all_files)
                        serialized["artifact_count"] = len(all_files)
                    except Exception as exc:
                        _log.warning("artifact_save_failed job=%s error=%s", job_id, exc)

                job_store.update(job_id, status="completed", result=serialized)
                metrics.record_job_completed(mode=req.mode, duration_s=time.time() - job_start)
                _log.info("generation_completed", extra={"job_id": job_id, "success": result.success})
                webhook_registry.fire("job.completed", job_id, get_tenant_id(), {"success": True})
                job_meta = job_store.get(job_id) or {}
                meta = job_meta.get("meta", {})
                notification_service.notify_async(
                    job_id=job_id,
                    status="completed",
                    result=serialized,
                    duration_s=time.time() - job_start,
                    tenant_id=meta.get("tenant_id", "default"),
                    slack_url=meta.get("slack_webhook", ""),
                    teams_url=meta.get("teams_webhook", ""),
                )
        except Exception as exc:
            _log.exception("generation_failed", extra={"job_id": job_id, "error": str(exc)})
            job_store.update(job_id, status="failed", error=str(exc))
            metrics.record_job_failed(mode=req.mode)
            webhook_registry.fire("job.failed", job_id, get_tenant_id(), {"error": str(exc)})
            job_meta = job_store.get(job_id) or {}
            meta = job_meta.get("meta", {})
            notification_service.notify_async(
                job_id=job_id,
                status="failed",
                result=None,
                duration_s=time.time() - job_start,
                tenant_id=meta.get("tenant_id", "default"),
                slack_url=meta.get("slack_webhook", ""),
                teams_url=meta.get("teams_webhook", ""),
            )


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
    setup_tracing("datasphere-api")
    _log.info("datasphere_api_starting", extra={"version": _VERSION})
    # Startup: load plugins
    plugin_registry.load()
    _log.info("plugins_loaded count=%d", len(plugin_registry.list_all()))
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
        description="""
# DataSphere Autonomous Data Platform API

API REST pour la génération automatique d'architectures data complètes.

## Fonctionnalités principales

- **Génération d'architecture** — 6 agents IA analysent votre besoin et génèrent une stack complète
- **Générateurs de code** — dbt, Airflow, Dagster, Prefect, Terraform
- **Analyse** — estimation de coûts multi-cloud, plan de migration, diagramme de lineage
- **Templates** — stacks prédéfinis pour démarrer rapidement
- **Webhooks** — notifications HTTP quand un job se termine
- **Métriques** — endpoint Prometheus-compatible `/metrics`

## Authentification

Optionnelle — activée en définissant `DATASPHERE_API_KEY` en variable d'environnement.

```
Authorization: Bearer <votre-clé>
```

## Multi-tenant

Isolez vos jobs par tenant via le header `X-Tenant-ID`.

## Streaming (SSE)

```
POST /generate → job_id
GET /generate/stream?job_id=<id> → EventSource
```
        """,
        version=_VERSION,
        contact={
            "name": "DataSphere Team",
            "url": "https://github.com/skaba89/datasphere-autonomous-data-platform",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
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
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Tenant-ID", "X-Slack-Webhook", "X-Teams-Webhook"],
    )

    # ------------------------------------------------------------------
    # Request ID + Rate limiting middleware
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def _request_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(req_id)

        # Tenant extraction and validation
        tenant_id = request.headers.get("X-Tenant-ID", "default")
        if not validate_tenant_id(tenant_id):
            return Response(
                content='{"detail":"Invalid X-Tenant-ID"}',
                status_code=400,
                headers={"Content-Type": "application/json"},
            )
        set_tenant_id(tenant_id)

        # Rate limiting on mutation endpoints — per tenant:ip bucket
        if request.method in ("POST", "PUT", "DELETE"):
            ip = request.client.host if request.client else "unknown"
            rate_key = f"{tenant_id}:{ip}"
            if not _rate_limiter.is_allowed(rate_key):
                _log.warning("rate_limit_exceeded", extra={"ip": ip, "tenant_id": tenant_id, "path": request.url.path})
                return Response(
                    content='{"detail":"Too many requests — rate limit exceeded"}',
                    status_code=429,
                    headers={"Content-Type": "application/json", "Retry-After": "60"},
                )

        start = time.monotonic()
        with start_span("http.request", {"http.method": request.method, "http.path": request.url.path}) as span:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000)
            span.set_attribute("http.status_code", response.status_code)
        metrics.record_http_request(
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - start),
        )
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        response.headers["X-Tenant-ID"] = tenant_id
        response.headers["X-API-Version"] = "1"
        # Add deprecation headers for unversioned routes (not /v1, not system/ui paths)
        _system_paths = {"/healthz", "/readyz", "/health", "/metrics", "/ui", "/ui/",
                         "/docs", "/redoc", "/openapi.json", "/"}
        path = request.url.path
        if (not path.startswith("/v1")
                and path not in _system_paths
                and not path.startswith("/ui")):
            response.headers["Deprecation"] = "true"
            # Build successor link — strip leading slash for formatting
            response.headers["Link"] = f'</v1{path}>; rel="successor-version"'
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

        # Check artifact store is accessible
        try:
            artifact_store.list_files("__health_check__")
            checks["artifact_store"] = "ok"
        except Exception as exc:
            checks["artifact_store"] = f"error: {exc}"
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
            "api_versions": {
                "v1": "/v1",
                "current": "v1",
                "deprecated": ["unversioned (no /v1 prefix)"],
            },
            "ui":   "/ui",
            "docs": "/docs",
            "health": "/health",
            "endpoints": [
                "GET  /ui  → Interface web",
                "POST /v1/generate",
                "GET  /v1/generate/stream?job_id=<id>",
                "GET  /v1/healthz  /v1/readyz",
                "GET  /v1/jobs/{job_id}",
                "POST /v1/proposals",
                "POST /v1/dbt/generate",
                "POST /v1/dags/airflow/generate",
                "POST /v1/dagster/generate",
                "POST /v1/prefect/generate",
                "POST /v1/terraform/generate",
                "GET  /v1/stacks/supported",
                "Multi-tenant: set X-Tenant-ID header to isolate jobs per tenant",
                "GET  /v1/metrics  → Prometheus metrics",
                "GET  /v1/plugins",
                "NOTE: Unversioned routes (without /v1) are deprecated and return Deprecation: true header",
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
        scoped_id = tenant_job_id(job_id)
        actual_id = scoped_id if job_store.get(scoped_id) else job_id
        if not job_store.get(actual_id):
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return make_sse_response(actual_id)

    @app.post(
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
        background_tasks.add_task(_run_generation, scoped_id, req)
        return JobResponse(
            job_id=job_id,
            status="pending",
            message=f"Génération lancée. Interrogez GET /jobs/{job_id}",
        )

    @app.post(
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

    # ------------------------------------------------------------------
    # Job status
    # ------------------------------------------------------------------

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["generation"])
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

    @app.get("/jobs", tags=["generation"])
    def list_jobs() -> list[dict]:
        """Liste tous les jobs filtrés par tenant courant."""
        all_jobs = job_store.list_all()
        tenant = get_tenant_id()
        if tenant != "default":
            prefix = f"{tenant}:"
            return [j for j in all_jobs if j["job_id"].startswith(prefix)]
        return [j for j in all_jobs if ":" not in j["job_id"]]

    @app.delete("/jobs/{job_id}", tags=["generation"])
    def delete_job(job_id: str) -> dict:
        """Supprime un job de l'historique."""
        scoped_id = tenant_job_id(job_id)
        if not (job_store.get(scoped_id) or job_store.get(job_id)):
            raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
        job_store.delete(scoped_id)
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

    # ------------------------------------------------------------------
    # Artifact storage endpoints
    # ------------------------------------------------------------------

    @app.get("/artifacts/{job_id}/download", tags=["artifacts"])
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

    @app.get("/artifacts/{job_id}", tags=["artifacts"])
    def list_artifacts(job_id: str) -> dict:
        """List all stored artifacts for a job."""
        files = artifact_store.list_files(job_id)
        return {"job_id": job_id, "files": files, "count": len(files)}

    @app.get("/artifacts/{job_id}/{filename:path}", tags=["artifacts"])
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

    @app.post("/jobs/purge", tags=["generation"])
    def purge_jobs(max_age_hours: int = 24) -> dict:
        """Supprime les jobs plus vieux que max_age_hours."""
        deleted = job_store.purge_old(max_age_hours * 3600)
        return {"deleted_count": deleted}

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    @app.post("/webhooks", tags=["webhooks"])
    def register_webhook(req: WebhookRegisterRequest, _: None = Depends(require_auth)) -> dict:
        """Register a webhook URL to be notified on job events."""
        tenant_id = get_tenant_id()
        wh = webhook_registry.register(req.url, tenant_id, req.events, req.secret)
        return {"id": wh.id, "url": wh.url, "events": wh.events, "created_at": wh.created_at}

    @app.get("/webhooks", tags=["webhooks"])
    def list_webhooks(_: None = Depends(require_auth)) -> list[dict]:
        """List all webhooks for current tenant."""
        tenant_id = get_tenant_id()
        return [{"id": w.id, "url": w.url, "events": w.events, "active": w.active}
                for w in webhook_registry.list_for_tenant(tenant_id)]

    @app.get("/webhooks/deliveries", tags=["webhooks"])
    def webhook_deliveries(_: None = Depends(require_auth)) -> list[dict]:
        """Recent webhook delivery attempts for current tenant."""
        return webhook_registry.recent_deliveries(get_tenant_id())

    @app.delete("/webhooks/{webhook_id}", tags=["webhooks"])
    def delete_webhook(webhook_id: str, _: None = Depends(require_auth)) -> dict:
        """Unregister a webhook."""
        tenant_id = get_tenant_id()
        if not webhook_registry.unregister(webhook_id, tenant_id):
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"deleted": webhook_id}

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

    @app.post(
        "/dbt/generate",
        tags=["generators"],
        summary="Génération de projet dbt",
        description="""
Génère un scaffold dbt complet prêt à l'emploi.

**Fichiers générés:**
- `dbt_project.yml` — configuration du projet
- `profiles.yml` — connexion au data warehouse
- `models/staging/` — modèles de staging par source
- `models/marts/` — modèles de marts analytiques
- `tests/` — tests génériques et singuliers
- `macros/` — macros utilitaires

Le nom du projet est dérivé du `business_request`.
        """,
        response_description="Projet dbt avec le contenu de chaque fichier généré",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "ventes_snowflake": {
                                "summary": "Analyse ventes sur Snowflake",
                                "value": DBT_REQUEST_EXAMPLE,
                            },
                            "full_stack": {
                                "summary": "Stack complète AWS",
                                "value": {
                                    "business_request": "Pipeline e-commerce complet",
                                    "cloud_provider": "aws",
                                    "data_warehouse": "snowflake",
                                    "orchestrator": "airflow",
                                    "ingestion": "airbyte",
                                    "transformation": "dbt",
                                    "bi_tool": "metabase",
                                    "deployment": "kubernetes",
                                    "security": ["RBAC"],
                                    "budget": "medium",
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
                                "project_name": "ventes_par_region",
                                "warehouse": "snowflake",
                                "file_count": 8,
                                "files": {
                                    "dbt_project.yml": "name: ventes_par_region\n...",
                                    "profiles.yml": "ventes_par_region:\n  target: dev\n...",
                                },
                            }
                        }
                    }
                }
            },
        },
    )
    def generate_dbt_project(req: DbtGenerateRequest) -> dict:
        """Génère un scaffold dbt complet (dbt_project.yml, profiles.yml, modèles, tests)."""
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

    @app.post(
        "/terraform/generate",
        tags=["generators"],
        summary="Génération de projet Terraform",
        description="""
Génère un projet Terraform complet pour déployer l'infrastructure data.

**Modules générés:**
- `providers.tf` — configuration des providers cloud (AWS/GCP/Azure)
- `networking/` — VPC, subnets, security groups
- `warehouse/` — Snowflake / BigQuery / Redshift
- `kubernetes/` — EKS / GKE / AKS cluster
- `iam/` — rôles, policies, service accounts
- `variables.tf` + `outputs.tf`

Utilise les modules Terraform officiels des providers cloud.
        """,
        response_description="Projet Terraform avec le contenu de chaque fichier .tf",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "aws_snowflake_k8s": {
                                "summary": "AWS + Snowflake + Kubernetes",
                                "value": TERRAFORM_REQUEST_EXAMPLE,
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
                                "provider": "aws",
                                "warehouse": "snowflake",
                                "file_count": 12,
                                "files": {
                                    "providers.tf": 'terraform {\n  required_providers {\n    aws = {}\n  }\n}\n',
                                    "networking/main.tf": "# VPC configuration\n...",
                                },
                            }
                        }
                    }
                }
            },
        },
    )
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

    @app.post(
        "/lineage/generate",
        tags=["generators"],
        summary="Génération du diagramme de lineage",
        description="""
Génère un diagramme de lineage des données au format **Mermaid** depuis une stack validée.

Le diagramme représente le flux de données de l'ingestion jusqu'au BI tool:

```
Source → Ingestion → Data Lake → Warehouse → Transformation → BI
```

**Résultat:**
- `mermaid` — code Mermaid embedable directement dans Markdown/Notion
- `nodes` — liste des noeuds du graphe
- `edge_count` — nombre de connexions
- `embed_url` — URL mermaid.live pour visualisation directe
        """,
        response_description="Diagramme Mermaid et métadonnées du graphe de lineage",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "stack_complete": {
                                "summary": "Stack AWS complète avec quality",
                                "value": LINEAGE_REQUEST_EXAMPLE,
                            },
                            "minimal": {
                                "summary": "Stack minimale",
                                "value": {
                                    "stack": {
                                        "cloud_provider": "gcp",
                                        "data_warehouse": "bigquery",
                                        "orchestrator": "dagster",
                                        "ingestion": "airbyte",
                                        "transformation": "dbt",
                                        "bi_tool": "looker",
                                    }
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
                                "mermaid": "graph LR\n  Source-->Airbyte-->Snowflake-->dbt-->Metabase",
                                "nodes": ["Source", "Airbyte", "Snowflake", "dbt", "Metabase"],
                                "edge_count": 4,
                                "embed_url": "https://mermaid.live/edit#...",
                            }
                        }
                    }
                }
            },
        },
    )
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

    @app.post(
        "/costs/estimate",
        tags=["analysis"],
        summary="Estimation des coûts de la stack",
        description="""
Calcule une estimation détaillée des coûts mensuels et annuels pour une stack donnée.

**Inclut:**
- Détail par composant (warehouse, orchestration, ingestion, BI…)
- Comparaison multi-cloud (AWS vs GCP vs Azure)
- Conseils d'optimisation des coûts
- Tiers budget: `low` / `medium` / `high`

Les prix sont basés sur les tarifs publics des fournisseurs cloud (mis à jour périodiquement).
        """,
        response_description="Estimation des coûts avec détail par composant et comparaison multi-cloud",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "aws_medium": {
                                "summary": "Stack AWS budget medium",
                                "value": COST_ESTIMATE_REQUEST_EXAMPLE,
                            },
                            "gcp_low": {
                                "summary": "Stack GCP budget low",
                                "value": {
                                    "stack": {
                                        "cloud_provider": "gcp",
                                        "data_warehouse": "bigquery",
                                        "orchestrator": "dagster",
                                        "ingestion": "airbyte",
                                        "transformation": "dbt",
                                        "bi_tool": "metabase",
                                    },
                                    "budget": "low",
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
                                "total_monthly_usd": 1250,
                                "total_yearly_usd": 15000,
                                "budget_tier": "medium",
                                "line_items": [
                                    {"component": "data_warehouse", "tool": "snowflake", "monthly_usd": 400, "yearly_usd": 4800, "notes": "Standard edition"},
                                    {"component": "orchestrator", "tool": "airflow", "monthly_usd": 150, "yearly_usd": 1800, "notes": "MWAA managed"},
                                ],
                                "savings_tips": ["Consider Snowflake auto-suspend", "Use spot instances for Airflow workers"],
                                "comparison": {"aws": 1250, "gcp": 1100, "azure": 1350},
                            }
                        }
                    }
                }
            },
        },
    )
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

    @app.post(
        "/stacks/diff",
        tags=["analysis"],
        summary="Comparaison et plan de migration entre deux stacks",
        description="""
Compare deux stacks et génère un plan de migration détaillé.

**Résultat:**
- `summary` — résumé textuel des changements
- `changes` — liste des composants modifiés avec effort/risque/étapes
- `migration_order` — ordre recommandé pour migrer sans interruption
- `rollback_strategy` — stratégie de rollback si la migration échoue
- `total_estimated_days` — durée totale estimée

**Niveaux de risque:** `low` / `medium` / `high` / `critical`
**Niveaux d'effort:** `low` / `medium` / `high`
        """,
        response_description="Plan de migration avec les changements détaillés entre les deux stacks",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "redshift_to_snowflake": {
                                "summary": "Migration Redshift → Snowflake + Dagster",
                                "value": STACK_DIFF_REQUEST_EXAMPLE,
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
                                "summary": "Migration de Redshift/Airflow vers Snowflake/Dagster",
                                "total_estimated_days": 45,
                                "overall_risk": "medium",
                                "migration_order": ["data_warehouse", "ingestion", "orchestrator", "bi_tool"],
                                "rollback_strategy": "Keep Redshift running in parallel for 30 days",
                                "changes": [
                                    {
                                        "component": "data_warehouse",
                                        "from_tool": "redshift",
                                        "to_tool": "snowflake",
                                        "change_type": "replace",
                                        "effort": "high",
                                        "risk": "medium",
                                        "estimated_days": 20,
                                        "migration_steps": ["Export data", "Transform schemas", "Load to Snowflake", "Validate"],
                                    }
                                ],
                            }
                        }
                    }
                }
            },
        },
    )
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
    # Stack templates
    # ------------------------------------------------------------------

    from datasphere.generators.templates import template_registry as _template_registry

    @app.get("/templates", tags=["templates"])
    def list_templates(category: str | None = None, budget: str | None = None) -> dict:
        """List all predefined stack templates, optionally filtered by category or budget."""
        templates = _template_registry.list_all()
        if category:
            templates = [t for t in templates if t.category == category]
        if budget:
            templates = [t for t in templates if t.constraints.get("budget") == budget]
        return {
            "count": len(templates),
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "complexity": t.complexity,
                    "estimated_monthly_usd": t.estimated_monthly_usd,
                    "time_to_deploy": t.time_to_deploy,
                    "tags": t.tags,
                    "pros": t.pros[:3],
                    "cons": t.cons[:2],
                    "use_cases": t.use_cases,
                    "stack": t.constraints,
                }
                for t in templates
            ],
        }

    @app.get("/templates/{template_id}", tags=["templates"])
    def get_template(template_id: str) -> dict:
        """Get a specific template by ID."""
        t = _template_registry.get(template_id)
        if not t:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        return {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "complexity": t.complexity,
            "estimated_monthly_usd": t.estimated_monthly_usd,
            "time_to_deploy": t.time_to_deploy,
            "constraints": t.constraints,
            "tags": t.tags,
            "pros": t.pros,
            "cons": t.cons,
            "use_cases": t.use_cases,
        }

    @app.post("/generate/from-template", response_model=JobResponse, tags=["generation"])
    async def generate_from_template(
        req: TemplateGenerateRequest,
        background_tasks: BackgroundTasks,
        _: None = Depends(require_auth),
    ) -> JobResponse:
        """Generate architecture from a predefined template with optional overrides."""
        t = _template_registry.get(req.template_id)
        if not t:
            raise HTTPException(status_code=404, detail=f"Template '{req.template_id}' not found")

        constraints = {**t.constraints, **req.overrides}

        # Map template constraint keys to GenerateRequest field names
        _field_map = {
            "cloud": "cloud_provider",
            "warehouse": "data_warehouse",
        }
        mapped: dict = {}
        for k, v in constraints.items():
            mapped_key = _field_map.get(k, k)
            if mapped_key in GenerateRequest.model_fields:
                mapped[mapped_key] = v

        generate_req = GenerateRequest(
            mode="explicit",
            business_request=req.business_request,
            **mapped,
        )

        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="pending", meta={"template_id": req.template_id})
        background_tasks.add_task(_run_generation, job_id, generate_req)
        return JobResponse(
            job_id=job_id,
            status="pending",
            message=f"Génération depuis template {req.template_id} lancée",
        )

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

    @app.get("/plugins", tags=["system"])
    def list_plugins() -> dict:
        """List all available generator plugins (built-in + installed)."""
        plugin_registry.load()
        plugins = plugin_registry.list_all()
        return {
            "count": len(plugins),
            "plugins": [p.to_dict() for p in plugins],
            "builtin_count": sum(1 for p in plugins if p.source == "builtin"),
            "external_count": sum(1 for p in plugins if p.source == "plugin"),
        }

    @app.get("/metrics", tags=["system"], response_class=PlainTextResponse)
    def prometheus_metrics() -> PlainTextResponse:
        """
        Prometheus-compatible metrics endpoint.

        Metrics: http_requests_total, http_request_duration_seconds,
        jobs_created_total, jobs_completed_total, jobs_failed_total,
        generation_duration_seconds, uptime_seconds.
        """
        return PlainTextResponse(
            content=metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # API versioning: register all existing routes under /v1/ prefix
    # ------------------------------------------------------------------
    from fastapi.routing import APIRoute as _APIRoute

    _skip_paths = {"/docs", "/redoc", "/openapi.json", "/", "/ui", "/ui/"}

    for _route in list(app.routes):
        if not isinstance(_route, _APIRoute):
            continue
        if _route.path.startswith("/v1"):
            continue
        if _route.path in _skip_paths:
            continue
        app.add_api_route(
            f"/v1{_route.path}",
            _route.endpoint,
            methods=list(_route.methods or ["GET"]),
            tags=[f"v1/{t}" for t in (_route.tags or [])],
            summary=_route.summary,
            description=_route.description,
            response_model=_route.response_model,
            include_in_schema=True,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point (uvicorn datasphere.api.app:app)
# ---------------------------------------------------------------------------

app = create_app()
