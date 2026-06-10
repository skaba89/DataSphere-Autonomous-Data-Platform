"""API REST FastAPI — expose DataSphere en tant que service HTTP."""
from __future__ import annotations
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import datasphere.adapters  # noqa: F401 — trigger adapter registry population
from datasphere.models.request import ArchitectureConstraints, BusinessRequest
from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.agents.mode_router import run_explicit, run_recommended
from datasphere.agents.proposer import generate_proposals
from datasphere.generators.dbt_project import DbtProjectGenerator
from datasphere.generators.airflow_dag import AirflowDagGenerator


# ---------------------------------------------------------------------------
# In-memory job store (swappable for Redis/DB in production)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}


def _store_job(job_id: str, status: str, result: Any = None, error: str = "") -> None:
    _jobs[job_id] = {"job_id": job_id, "status": status, "result": result, "error": error}


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    mode: str = Field("explicit", description="'explicit' ou 'recommended'")
    # Mode 1 — explicit
    business_request: Optional[str] = None
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
    business_request: str
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
    business_request: str
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


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

def _run_generation(job_id: str, req: GenerateRequest) -> None:
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
            _store_job(job_id, "completed", serialized)
    except Exception as exc:
        _store_job(job_id, "failed", error=str(exc))


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


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="DataSphere API",
        description=(
            "API REST pour la génération automatique d'architectures data.\n\n"
            "**Mode 1** — Stack explicite : vous choisissez chaque outil.\n\n"
            "**Mode 2** — Stack recommandée : vous donnez budget/volume/équipe, "
            "les agents recommandent."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": "1.0.0", "timestamp": time.time()}

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": "DataSphere Autonomous Data Platform",
            "docs": "/docs",
            "health": "/health",
            "endpoints": [
                "POST /generate",
                "GET  /jobs/{job_id}",
                "POST /proposals",
                "POST /dbt/generate",
                "POST /dags/airflow/generate",
                "GET  /stacks/supported",
            ],
        }

    # ------------------------------------------------------------------
    # Async generation
    # ------------------------------------------------------------------

    @app.post("/generate", response_model=JobResponse, tags=["generation"])
    async def generate(req: GenerateRequest, background_tasks: BackgroundTasks) -> JobResponse:
        """
        Lance la génération asynchrone d'une architecture data complète.

        Retourne un `job_id` à interroger via `GET /jobs/{job_id}`.
        """
        if req.mode not in ("explicit", "recommended"):
            raise HTTPException(status_code=422, detail="mode doit être 'explicit' ou 'recommended'")
        if not req.business_request:
            raise HTTPException(status_code=422, detail="business_request est requis")

        job_id = str(uuid.uuid4())
        _store_job(job_id, "pending")
        background_tasks.add_task(_run_generation, job_id, req)
        return JobResponse(
            job_id=job_id,
            status="pending",
            message=f"Génération lancée. Interrogez GET /jobs/{job_id}",
        )

    @app.post("/generate/sync", tags=["generation"])
    async def generate_sync(req: GenerateRequest) -> dict:
        """
        Génération synchrone (bloquante). Pour les petites architectures ou tests.
        """
        if req.mode not in ("explicit", "recommended"):
            raise HTTPException(status_code=422, detail="mode doit être 'explicit' ou 'recommended'")
        if not req.business_request:
            raise HTTPException(status_code=422, detail="business_request est requis")

        job_id = str(uuid.uuid4())
        _store_job(job_id, "pending")
        _run_generation(job_id, req)
        job = _jobs.get(job_id, {})
        if job.get("status") == "failed":
            raise HTTPException(status_code=500, detail=job.get("error", "Generation failed"))
        return job.get("result", {})

    # ------------------------------------------------------------------
    # Job status
    # ------------------------------------------------------------------

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["generation"])
    def get_job(job_id: str) -> JobStatusResponse:
        """Récupère le statut et le résultat d'un job de génération."""
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} non trouvé")
        return JobStatusResponse(**job)

    @app.get("/jobs", tags=["generation"])
    def list_jobs() -> list[dict]:
        """Liste tous les jobs (en mémoire — non persistant)."""
        return [{"job_id": jid, "status": j["status"]} for jid, j in _jobs.items()]

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
