"""Generator routes: /dbt/generate, /dags/airflow/generate, /dagster, /prefect, /terraform, /lineage."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from datasphere.models.request import ArchitectureConstraints
from datasphere.generators.dbt_project import DbtProjectGenerator
from datasphere.generators.airflow_dag import AirflowDagGenerator
from datasphere.generators.dagster_job import DagsterJobGenerator
from datasphere.generators.prefect_flow import PrefectFlowGenerator
from datasphere.api.models import DbtGenerateRequest, DagGenerateRequest, LineageRequest
from datasphere.api.openapi_examples import (
    DBT_REQUEST_EXAMPLE,
    TERRAFORM_REQUEST_EXAMPLE,
    LINEAGE_REQUEST_EXAMPLE,
)

router = APIRouter(tags=["generators"])


@router.post(
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


@router.post("/dags/airflow/generate", tags=["generators"])
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


@router.post("/dagster/generate", tags=["generators"])
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


@router.post("/prefect/generate", tags=["generators"])
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


@router.post(
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


@router.post(
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
