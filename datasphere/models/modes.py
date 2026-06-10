"""
Input models for the two platform modes.

MODE 1 — Explicit Stack
  Human provides every tool choice. Agents validate, generate infra and CI/CD.

MODE 2 — Recommended Stack
  Human provides only context (budget, volume, security, team, cloud preference).
  Agents propose 2-3 architectures; human validates one; agents generate everything.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Shared ───────────────────────────────────────────────────────────────────

TeamSize = Literal["solo", "small", "medium", "large"]
# solo   = 1 person
# small  = 2-5 people
# medium = 6-15 people
# large  = 15+ people

SecurityLevel = Literal["simple", "rbac", "enterprise"]
# simple     = .env secrets, SSL, basic auth
# rbac       = role-based access control, JWT
# enterprise = SSO/OIDC, Vault, RBAC, RLS, audit logs

Budget = Literal["low", "medium", "enterprise"]
DataVolume = Literal["small", "medium", "large", "xlarge"]
ProcessingMode = Literal["batch", "realtime", "both"]
CloudPreference = Literal[
    "none", "aws", "azure", "gcp",
    "local-docker", "kubernetes", "ovhcloud", "scaleway", "on-premise"
]


# ── MODE 1 — Explicit Stack ───────────────────────────────────────────────────

class ExplicitStack(BaseModel):
    """
    MODE 1 — All tools explicitly chosen by the human.
    Agents validate compatibility, generate infrastructure and CI/CD.
    """
    mode: Literal["explicit"] = "explicit"
    business_request: str = Field(..., description="Besoin métier en langage naturel")

    # Required
    cloud_provider: str = Field(..., description="ex: aws, gcp, azure, local-docker")
    data_warehouse: str = Field(..., description="ex: snowflake, bigquery, postgresql")
    orchestrator:   str = Field(..., description="ex: airflow, dagster, prefect")
    ingestion:      str = Field(..., description="ex: airbyte, meltano, kafka-connect")
    transformation: str = Field(..., description="ex: dbt, sqlmesh, spark")
    bi_tool:        str = Field(..., description="ex: superset, metabase, powerbi")
    deployment:     str = Field(..., description="ex: docker-compose, kubernetes, terraform")

    # Optional
    data_lake:      Optional[str] = Field(None, description="ex: s3, minio, gcs")
    catalog:        Optional[str] = Field(None, description="ex: openmetadata, datahub")
    quality:        Optional[str] = Field(None, description="ex: great-expectations, soda-core")
    ai_tool:        Optional[str] = Field(None, description="ex: openai, anthropic, ollama")
    vector_db:      Optional[str] = Field(None, description="ex: qdrant, pgvector, chroma")
    iac:            Optional[str] = Field(None, description="ex: terraform, helm")
    security:       list[str]    = Field(default_factory=list, description="ex: [RBAC, Vault, RLS]")
    budget:         Budget       = "medium"
    data_volume:    DataVolume   = "medium"
    processing_mode: ProcessingMode = "batch"
    region:         Optional[str] = None
    environment:    Literal["development", "staging", "production"] = "production"

    def to_architecture_constraints(self):
        """Convert to ArchitectureConstraints for the generation pipeline."""
        from datasphere.models.request import ArchitectureConstraints
        return ArchitectureConstraints(
            cloud_provider=self.cloud_provider,
            data_warehouse=self.data_warehouse,
            orchestrator=self.orchestrator,
            ingestion=self.ingestion,
            transformation=self.transformation,
            data_lake=self.data_lake,
            bi_tool=self.bi_tool,
            catalog=self.catalog,
            quality=self.quality,
            deployment=self.deployment,
            iac=self.iac or _infer_iac(self.deployment),
            security=self.security or ["RBAC"],
            budget=self.budget,
            data_volume=self.data_volume,
            processing_mode=self.processing_mode,
            region=self.region,
        )


# ── MODE 2 — Recommended Stack ────────────────────────────────────────────────

class RecommendationContext(BaseModel):
    """
    MODE 2 — Human provides only context, agents recommend the architecture.
    No tool names required — only business and operational constraints.
    """
    mode: Literal["recommended"] = "recommended"
    business_request: str = Field(..., description="Besoin métier en langage naturel")

    # Business context
    budget:          Budget      = Field(..., description="Budget disponible")
    data_volume:     DataVolume  = Field(..., description="Volume de données attendu")
    security_level:  SecurityLevel = Field(..., description="Niveau de sécurité requis")
    team_size:       TeamSize    = Field(..., description="Taille de l'équipe data")
    processing_mode: ProcessingMode = Field("batch", description="Mode batch, temps réel ou les deux")

    # Optional preferences (not mandatory)
    cloud_preference: CloudPreference = Field(
        "none",
        description="Cloud préféré — 'none' si pas de préférence"
    )
    deployment_preference: Optional[Literal["docker-compose", "kubernetes", "managed"]] = Field(
        None,
        description="Préférence de déploiement — None si pas de préférence"
    )
    must_be_open_source: bool = Field(
        False,
        description="Si True, exclut tous les outils SaaS payants"
    )
    existing_tools: list[str] = Field(
        default_factory=list,
        description="Outils déjà en place que les agents doivent prendre en compte"
    )
    compliance_requirements: list[str] = Field(
        default_factory=list,
        description="Exigences de conformité : RGPD, HIPAA, HDS, SOX, PCI-DSS…"
    )

    def to_raw_constraints(self) -> dict:
        """Convert to the raw dict format used by the proposer."""
        security_map: dict[str, list[str]] = {
            "simple":     ["jwt"],
            "rbac":       ["RBAC", "jwt"],
            "enterprise": ["RBAC", "RLS", "Vault"],
        }
        budget_to_deployment = {
            "low":        "docker-compose",
            "medium":     "kubernetes",
            "enterprise": "kubernetes",
        }
        team_to_complexity = {
            "solo":   "low",
            "small":  "medium",
            "medium": "medium",
            "large":  "high",
        }
        cloud = self.cloud_preference if self.cloud_preference != "none" else "local-docker"
        deployment = self.deployment_preference or budget_to_deployment[self.budget]
        iac = {"docker-compose": "docker-compose", "kubernetes": "helm", "managed": "terraform"}[deployment]

        return {
            "cloud_provider":  cloud,
            "budget":          "low" if self.must_be_open_source else self.budget,
            "data_volume":     self.data_volume,
            "processing_mode": self.processing_mode,
            "security":        security_map[self.security_level],
            "deployment":      deployment,
            "iac":             iac,
            "region":          None,
            # Resolved by proposer
            "data_warehouse":  "auto",
            "orchestrator":    "auto",
            "ingestion":       "auto",
            "transformation":  "auto",
            "data_lake":       "auto",
            "bi_tool":         "auto",
            "catalog":         "auto",
            "quality":         "auto",
            # Metadata for proposer scoring
            "_team_size":            self.team_size,
            "_must_be_open_source":  self.must_be_open_source,
            "_existing_tools":       self.existing_tools,
            "_compliance":           self.compliance_requirements,
        }


def _infer_iac(deployment: str) -> str:
    return {
        "docker-compose": "docker-compose",
        "Docker Compose": "docker-compose",
        "kubernetes":     "helm",
        "Kubernetes":     "helm",
        "helm":           "helm",
        "terraform":      "terraform",
        "Terraform":      "terraform",
        "managed":        "terraform",
    }.get(deployment, "docker-compose")
