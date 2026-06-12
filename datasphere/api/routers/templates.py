"""Template routes: /templates, /templates/{id}, /generate/from-template."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from datasphere.api.auth import require_auth
from datasphere.api.job_store import job_store
from datasphere.api.generation_utils import _run_generation
from datasphere.api.models import GenerateRequest, JobResponse, TemplateGenerateRequest
from datasphere.api.openapi_examples import TEMPLATE_GENERATE_EXAMPLE
from datasphere.generators.templates import template_registry as _template_registry

router = APIRouter(tags=["templates"])


@router.get(
    "/templates",
    tags=["templates"],
    summary="Lister les templates de stacks prédéfinis",
    description="""
Liste tous les templates de stacks data prédéfinis.

**Filtres disponibles:**
- `category` — catégorie du template (ex: `ecommerce`, `saas`, `startup`)
- `budget` — tier de budget: `low`, `medium`, `high`

Chaque template inclut:
- La stack complète (cloud + warehouse + orchestrateur + BI…)
- Estimation des coûts mensuels
- Délai de déploiement estimé
- Pros / cons
- Cas d'usage typiques

Utilisez `POST /generate/from-template` pour lancer une génération depuis un template.
    """,
    response_description="Liste des templates disponibles avec leurs métadonnées",
)
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


@router.get("/templates/{template_id}", tags=["templates"])
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


@router.post(
    "/generate/from-template",
    response_model=JobResponse,
    tags=["generation"],
    summary="Génération depuis un template prédéfini",
    description="""
Génère une architecture à partir d'un template prédéfini avec des surcharges optionnelles.

Utilisez `GET /templates` pour lister les templates disponibles.

**Surcharges (`overrides`):** remplacent les valeurs par défaut du template.
Par exemple, pour changer le BI tool d'un template AWS:
```json
{"overrides": {"bi_tool": "metabase"}}
```

Le job est lancé en arrière-plan — suivez l'avancement via `GET /jobs/{job_id}`.
    """,
    response_description="Job créé depuis le template avec son identifiant",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "modern_data_stack": {
                            "summary": "Modern Data Stack AWS avec override BI",
                            "value": TEMPLATE_GENERATE_EXAMPLE,
                        },
                        "minimal_override": {
                            "summary": "Template sans override",
                            "value": {
                                "template_id": "startup-gcp",
                                "business_request": "Analyse des logs applicatifs",
                                "overrides": {},
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
                            "message": "Génération depuis template modern-data-stack-aws lancée",
                        }
                    }
                }
            }
        },
    },
)
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
