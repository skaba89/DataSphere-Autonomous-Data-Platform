"""Analysis routes: /costs/estimate, /stacks/diff, /proposals."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from datasphere.agents.proposer import generate_proposals
from datasphere.api.models import CostEstimateRequest, ProposalsRequest, StackDiffRequest
from datasphere.api.openapi_examples import (
    COST_ESTIMATE_REQUEST_EXAMPLE,
    STACK_DIFF_REQUEST_EXAMPLE,
)

router = APIRouter(tags=["analysis"])


@router.post("/proposals", tags=["recommendations"])
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


@router.post(
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


@router.post(
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
