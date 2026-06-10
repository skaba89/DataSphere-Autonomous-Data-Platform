"""
Architecture Proposer — étape 3 du flow conversationnel.

Génère 2 ou 3 architectures distinctes à partir des contraintes collectées.
Chaque proposition a un nom, des avantages/inconvénients, un coût estimé.
"""
from __future__ import annotations
from datasphere.models.conversation import ArchitectureProposal
from datasphere.models.request import ArchitectureConstraints


# ---------------------------------------------------------------------------
# Architecture templates par profil
# ---------------------------------------------------------------------------

def _base(raw: dict) -> dict:
    """Fields common to all proposals — non-tool fields."""
    return {
        "cloud_provider":  raw["cloud_provider"],
        "budget":          raw["budget"],
        "data_volume":     raw["data_volume"],
        "processing_mode": raw["processing_mode"],
        "security":        raw["security"],
        "deployment":      raw["deployment"],
        "iac":             raw["iac"],
        "region":          raw.get("region"),
    }


def _cost(wh: str, budget: str, volume: str, mode: str) -> float:
    """Quick cost estimate in USD/month."""
    wh_cost = {
        "postgresql": 0, "duckdb": 0, "clickhouse": 0,
        "snowflake": 500, "bigquery": 200, "redshift": 600,
        "azure-synapse": 550, "databricks": 900,
    }.get(wh, 0)
    vol_mult = {"small": 0.5, "medium": 1.0, "large": 2.5, "xlarge": 8.0}.get(volume, 1.0)
    mode_mult = 1.4 if mode == "realtime" else 1.0
    base = {"low": 50, "medium": 150, "enterprise": 400}.get(budget, 150)
    return round((wh_cost + base) * vol_mult * mode_mult, 0)


# ------------------------------------------------------------------
# Proposal generators by cloud + budget + mode
# ------------------------------------------------------------------

def _proposal_open_source(raw: dict, idx: int) -> ArchitectureProposal:
    """Fully open-source — zero SaaS licences."""
    cloud = raw["cloud_provider"]
    mode = raw["processing_mode"]
    volume = raw["data_volume"]
    budget = raw["budget"]
    depl = raw["deployment"]

    wh = "clickhouse" if mode == "realtime" else "postgresql"
    orch = "dagster" if depl == "kubernetes" else "airflow"
    transform = "dbt"
    ingest = "meltano" if budget == "low" else "airbyte"
    storage = "minio" if cloud not in ("aws", "gcp", "azure") else {
        "aws": "s3", "gcp": "gcs", "azure": "adls"
    }[cloud]
    bi = "superset"
    quality = "dbt-tests"
    catalog = "openmetadata"

    return ArchitectureProposal(
        id=idx,
        name="Stack Open-Source Pure",
        tagline="Zéro licence — 100% open-source, contrôle total",
        constraints=ArchitectureConstraints(**_base(raw), **{
            "data_warehouse":  wh,
            "orchestrator":    orch,
            "ingestion":       ingest,
            "transformation":  transform,
            "data_lake":       storage,
            "bi_tool":         bi,
            "catalog":         catalog,
            "quality":         quality,
        }),
        pros=[
            "Zéro coût de licence — uniquement infra",
            "Contrôle total sur vos données",
            "Pas de dépendance fournisseur (vendor lock-in)",
            "Stack la plus populaire dans la communauté data",
        ],
        cons=[
            "Maintenance opérationnelle à votre charge",
            "Scalabilité limitée sans Kubernetes" if depl != "kubernetes" else "Expertise K8s requise",
            "Pas de support SLA garanti",
        ],
        estimated_monthly_usd=_cost(wh, budget, volume, mode),
        complexity="medium" if depl == "kubernetes" else "low",
        time_to_deploy="1–3 jours (local) / 1–2 semaines (prod)",
        best_for="Startups, équipes techniques, contrainte budgétaire forte",
    )


def _proposal_cloud_native(raw: dict, idx: int) -> ArchitectureProposal:
    """Cloud-native managed services — minimal ops."""
    cloud = raw["cloud_provider"]
    mode = raw["processing_mode"]
    volume = raw["data_volume"]
    budget = raw["budget"]

    wh_map = {
        "aws": "redshift", "gcp": "bigquery", "azure": "azure-synapse",
        "local-docker": "postgresql", "kubernetes": "postgresql",
        "ovhcloud": "postgresql", "scaleway": "postgresql", "on-premise": "postgresql",
    }
    wh = wh_map.get(cloud, "postgresql")

    storage_map = {"aws": "s3", "gcp": "gcs", "azure": "adls"}
    storage = storage_map.get(cloud, "minio")

    orch = {"aws": "airflow", "gcp": "prefect", "azure": "dagster"}.get(cloud, "dagster")
    ingest = "airbyte"
    transform = "dbt"
    bi_map = {"azure": "powerbi", "aws": "superset", "gcp": "superset"}
    bi = bi_map.get(cloud, "superset")
    quality = "great-expectations"
    catalog = "datahub" if budget == "enterprise" else "openmetadata"

    return ArchitectureProposal(
        id=idx,
        name=f"Stack Cloud-Native {cloud.upper()}",
        tagline=f"Services managés {cloud.upper()} — ops minimal, scalabilité automatique",
        constraints=ArchitectureConstraints(**_base(raw), **{
            "data_warehouse":  wh,
            "orchestrator":    orch,
            "ingestion":       ingest,
            "transformation":  transform,
            "data_lake":       storage,
            "bi_tool":         bi,
            "catalog":         catalog,
            "quality":         quality,
        }),
        pros=[
            f"Intégration native {cloud.upper()} — pas d'infra à gérer",
            "Auto-scaling selon la charge",
            "SLA et support cloud inclus",
            "Sécurité et conformité gérées par le cloud provider",
        ],
        cons=[
            f"Vendor lock-in {cloud.upper()}",
            "Coût plus élevé qu'une stack self-hosted",
            "Données hébergées chez un tiers" if cloud != "on-premise" else "",
        ],
        estimated_monthly_usd=_cost(wh, budget, volume, mode),
        complexity="low",
        time_to_deploy="3–7 jours avec Terraform",
        best_for=f"Équipes déjà sur {cloud.upper()}, priorité à la rapidité de mise en production",
    )


def _proposal_enterprise(raw: dict, idx: int) -> ArchitectureProposal:
    """Enterprise-grade — multi-cloud, best-of-breed, maximum robustness."""
    cloud = raw["cloud_provider"]
    mode = raw["processing_mode"]
    volume = raw["data_volume"]
    budget = raw["budget"]

    wh = "snowflake" if cloud not in ("gcp",) else "bigquery"
    orch = "dagster"
    ingest = "airbyte"
    transform = "dbt" if mode != "realtime" else "spark"
    storage_map = {"aws": "s3", "gcp": "gcs", "azure": "adls"}
    storage = storage_map.get(cloud, "minio")
    bi = "superset"
    quality = "soda-core"
    catalog = "datahub"

    return ArchitectureProposal(
        id=idx,
        name="Stack Enterprise Best-of-Breed",
        tagline="Maximum robustesse — Snowflake + Dagster + DataHub + Soda Core",
        constraints=ArchitectureConstraints(**_base(raw), **{
            "data_warehouse":  wh,
            "orchestrator":    orch,
            "ingestion":       ingest,
            "transformation":  transform,
            "data_lake":       storage,
            "bi_tool":         bi,
            "catalog":         catalog,
            "quality":         quality,
        }),
        pros=[
            "Outils leaders du marché sur chaque couche",
            "Support enterprise disponible sur chaque composant",
            "Séparation compute/storage (Snowflake) — coût optimisé à l'usage",
            "Observabilité et data lineage de bout en bout",
            "Prêt pour la conformité (SOX, RGPD, HIPAA)",
        ],
        cons=[
            f"Coût mensuel plus élevé (~${_cost(wh, budget, volume, mode):,.0f}/mois)",
            "Courbe d'apprentissage sur Dagster + Soda Core",
            "Snowflake : vendor lock-in modéré",
        ],
        estimated_monthly_usd=_cost(wh, budget, volume, mode),
        complexity="high",
        time_to_deploy="2–4 semaines",
        best_for="Scale-ups et entreprises, équipes data > 5 personnes, contraintes de compliance",
    )


def _proposal_realtime(raw: dict, idx: int) -> ArchitectureProposal:
    """Streaming-first — for realtime or both mode."""
    cloud = raw["cloud_provider"]
    volume = raw["data_volume"]
    budget = raw["budget"]
    depl = raw["deployment"]

    storage_map = {"aws": "s3", "gcp": "gcs", "azure": "adls"}
    storage = storage_map.get(cloud, "minio")

    return ArchitectureProposal(
        id=idx,
        name="Stack Streaming Temps Réel",
        tagline="Kafka + Flink + ClickHouse — latence sub-minute",
        constraints=ArchitectureConstraints(**_base(raw), **{
            "data_warehouse":  "clickhouse",
            "orchestrator":    "argo" if depl == "kubernetes" else "prefect",
            "ingestion":       "kafka-connect",
            "transformation":  "flink",
            "data_lake":       storage,
            "bi_tool":         "grafana",
            "catalog":         "openmetadata",
            "quality":         "great-expectations",
        }),
        pros=[
            "Latence < 1 minute de la source à la dashboard",
            "ClickHouse : requêtes analytiques en millisecondes",
            "Scalabilité horizontale native (Kafka + Flink)",
            "Idéal pour alertes, détection de fraude, monitoring temps réel",
        ],
        cons=[
            "Complexité opérationnelle élevée (Kafka + Flink + ClickHouse)",
            "Debugging plus difficile qu'en batch",
            "Pas adapté aux transformations SQL complexes type dbt",
        ],
        estimated_monthly_usd=_cost("clickhouse", budget, volume, "realtime"),
        complexity="high",
        time_to_deploy="3–6 semaines",
        best_for="Analytics temps réel, IoT, fraud detection, monitoring métrique",
    )


def _proposal_lightweight(raw: dict, idx: int) -> ArchitectureProposal:
    """Minimal footprint — for small volume or local."""
    cloud = raw["cloud_provider"]
    volume = raw["data_volume"]
    budget = raw["budget"]

    return ArchitectureProposal(
        id=idx,
        name="Stack Légère & Rapide",
        tagline="DuckDB + Prefect + Evidence — prêt en < 1 jour",
        constraints=ArchitectureConstraints(**_base(raw), **{
            "data_warehouse":  "duckdb",
            "orchestrator":    "prefect",
            "ingestion":       "meltano",
            "transformation":  "dbt",
            "data_lake":       "minio" if cloud not in ("aws", "gcp", "azure") else {
                "aws": "s3", "gcp": "gcs", "azure": "adls"
            }.get(cloud, "minio"),
            "bi_tool":         "evidence",
            "catalog":         "marquez",
            "quality":         "dbt-tests",
        }),
        pros=[
            "DuckDB : zéro serveur, SQL in-process ultra-rapide",
            "Evidence.dev : BI as code, rapports versionnés",
            "Déployable en < 1 jour",
            "Coût quasi nul — pas de serveur warehouse",
        ],
        cons=[
            "DuckDB : limité à ~100 Go en pratique",
            "Pas adapté aux équipes > 3-4 analystes concurrents",
            "Evidence.dev : courbe d'apprentissage pour les non-devs",
        ],
        estimated_monthly_usd=_cost("duckdb", budget, volume, "batch"),
        complexity="low",
        time_to_deploy="< 1 jour",
        best_for="POC, MVPs, petites équipes, exploration de données",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_proposals(raw: dict) -> list[ArchitectureProposal]:
    """
    Generate 3 differentiated architecture proposals from raw constraints.
    Always provides genuine alternatives — never just one default.
    """
    cloud = raw["cloud_provider"]
    budget = raw["budget"]
    mode = raw["processing_mode"]
    volume = raw["data_volume"]

    proposals: list[ArchitectureProposal] = []

    if mode == "realtime":
        # Realtime: always offer streaming as option 1
        proposals.append(_proposal_realtime(raw, 1))
        proposals.append(_proposal_open_source(raw, 2))
        if budget != "low":
            proposals.append(_proposal_cloud_native(raw, 3))
        else:
            proposals.append(_proposal_lightweight(raw, 3))

    elif volume in ("small",) or budget == "low":
        # Small/budget-constrained
        proposals.append(_proposal_lightweight(raw, 1))
        proposals.append(_proposal_open_source(raw, 2))
        if cloud in ("aws", "gcp", "azure") and budget != "low":
            proposals.append(_proposal_cloud_native(raw, 3))

    elif budget == "enterprise":
        # Enterprise: best-of-breed first
        proposals.append(_proposal_enterprise(raw, 1))
        proposals.append(_proposal_cloud_native(raw, 2))
        proposals.append(_proposal_open_source(raw, 3))

    elif cloud in ("aws", "gcp", "azure"):
        # Cloud with medium budget
        proposals.append(_proposal_cloud_native(raw, 1))
        proposals.append(_proposal_open_source(raw, 2))
        proposals.append(_proposal_enterprise(raw, 3))

    else:
        # Local / on-premise / kubernetes
        proposals.append(_proposal_open_source(raw, 1))
        proposals.append(_proposal_lightweight(raw, 2))
        if budget != "low":
            proposals.append(_proposal_enterprise(raw, 3))

    return proposals[:3]
