"""
Mode Router — entry point for the two platform modes.

MODE 1 (explicit):    Human specifies every tool. Agents validate + generate.
MODE 2 (recommended): Human gives context only. Agents propose 3 architectures,
                      human validates one, agents generate everything.

Interactive (CLI): run_interactive()
Programmatic:      run_explicit(ExplicitStack) / run_recommended(RecommendationContext)
"""
from __future__ import annotations
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box

from datasphere.models.modes import (
    ExplicitStack, RecommendationContext,
    Budget, DataVolume, SecurityLevel, TeamSize, ProcessingMode, CloudPreference,
)
from datasphere.models.conversation import ArchitectureProposal
from datasphere.models.output import OrchestratorOutput

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Interactive mode selection
# ─────────────────────────────────────────────────────────────────────────────

def run_interactive(output_dir: str = "./datasphere-artifacts") -> OrchestratorOutput:
    """Full interactive flow — asks human to choose Mode 1 or Mode 2 first."""
    console.print(Panel.fit(
        "[bold green]DataSphere — Plateforme de Données Autonome[/bold green]\n"
        "[dim]Stack-agnostic · Cloud-agnostic · Multi-agents[/dim]",
        border_style="green",
        padding=(1, 4),
    ))

    console.print(f"\n{Rule('[bold cyan]Quel mode souhaitez-vous ?[/bold cyan]')}")
    console.print()
    console.print(
        "  [bold cyan]1.[/bold cyan]  [bold]Mode Explicit[/bold]  — Je connais ma stack\n"
        "     [dim]Vous choisissez : AWS + Snowflake + Airflow + dbt + Superset…\n"
        "     Les agents valident la compatibilité et génèrent toute l'infrastructure.[/dim]\n"
    )
    console.print(
        "  [bold cyan]2.[/bold cyan]  [bold]Mode Recommandation[/bold]  — Recommandez-moi une architecture\n"
        "     [dim]Vous donnez : budget · volume · sécurité · équipe · cloud préféré\n"
        "     Les agents proposent 3 architectures, vous choisissez, ils génèrent tout.[/dim]\n"
    )

    while True:
        raw = console.input("  Votre choix [1 ou 2] : ").strip()
        if raw == "1":
            stack = _interactive_mode1()
            return run_explicit(stack, output_dir=output_dir)
        if raw == "2":
            ctx = _interactive_mode2()
            return run_recommended(ctx, output_dir=output_dir)
        console.print("  [red]Entrez 1 ou 2.[/red]")


# ─────────────────────────────────────────────────────────────────────────────
# MODE 1 — Interactive collection
# ─────────────────────────────────────────────────────────────────────────────

_CLOUD_OPTS = [
    ("local-docker", "Local Docker"), ("aws", "AWS"), ("azure", "Azure"),
    ("gcp", "GCP"), ("kubernetes", "Kubernetes existant"),
    ("ovhcloud", "OVHcloud"), ("scaleway", "Scaleway"), ("on-premise", "On-premise"),
]
_WH_OPTS = [
    ("postgresql", "PostgreSQL"), ("snowflake", "Snowflake"),
    ("bigquery", "BigQuery"), ("redshift", "Redshift"),
    ("azure-synapse", "Azure Synapse"), ("databricks", "Databricks"),
    ("clickhouse", "ClickHouse"), ("duckdb", "DuckDB"),
]
_ORCH_OPTS = [
    ("airflow", "Airflow"), ("dagster", "Dagster"), ("prefect", "Prefect"),
    ("argo", "Argo Workflows"), ("kestra", "Kestra"),
]
_INGEST_OPTS = [
    ("airbyte", "Airbyte"), ("meltano", "Meltano"), ("kafka-connect", "Kafka Connect"),
    ("debezium", "Debezium"), ("nifi", "Apache NiFi"),
]
_TRANSFORM_OPTS = [
    ("dbt", "dbt Core"), ("sqlmesh", "SQLMesh"), ("spark", "Apache Spark"),
    ("flink", "Apache Flink"), ("polars", "Python/Polars"),
]
_BI_OPTS = [
    ("superset", "Apache Superset"), ("metabase", "Metabase"),
    ("grafana", "Grafana"), ("powerbi", "Power BI"),
    ("tableau", "Tableau"), ("evidence", "Evidence.dev"), ("redash", "Redash"),
]
_STORAGE_OPTS = [
    ("minio", "MinIO (S3-compatible, self-hosted)"), ("s3", "AWS S3"),
    ("gcs", "Google Cloud Storage"), ("adls", "Azure Data Lake Storage"),
    ("none", "Pas de data lake"),
]
_DEPLOY_OPTS = [
    ("docker-compose", "Docker Compose"), ("kubernetes", "Kubernetes / Helm"),
    ("terraform", "Terraform (services managés cloud)"),
]
_SECURITY_OPTS = [
    ("simple",     "Simple — .env, SSL, basic auth"),
    ("rbac",       "RBAC — contrôle d'accès par rôle + JWT"),
    ("enterprise", "Enterprise — Vault + SSO/OIDC + RBAC + RLS + audit"),
]
_BUDGET_OPTS = [
    ("low",        "Faible — open-source uniquement"),
    ("medium",     "Moyen — quelques SaaS OK"),
    ("enterprise", "Enterprise — budget disponible"),
]
_VOLUME_OPTS = [
    ("small",  "Small  — < 10 Go/jour"),
    ("medium", "Medium — 10 Go–1 To/jour"),
    ("large",  "Large  — > 1 To/jour"),
    ("xlarge", "XLarge — > 10 To/jour ou streaming haute fréquence"),
]


def _pick(prompt: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    console.print(f"\n  [bold yellow]{prompt}[/bold yellow]")
    for i, (_, label) in enumerate(options, 1):
        marker = " [dim](défaut)[/dim]" if i - 1 == default_idx else ""
        console.print(f"    [cyan]{i}.[/cyan] {label}{marker}")
    while True:
        raw = console.input(f"    Choix [1-{len(options)}] (Entrée = défaut) : ").strip()
        if not raw:
            return options[default_idx][0]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        console.print("    [red]Invalide.[/red]")


def _ask_text(prompt: str, default: str = "") -> str:
    suffix = f" [dim](défaut: {default})[/dim]" if default else ""
    raw = console.input(f"  [bold yellow]{prompt}[/bold yellow]{suffix} : ").strip()
    return raw or default


def _interactive_mode1() -> ExplicitStack:
    console.print(f"\n{Rule('[bold cyan]Mode 1 — Stack Explicite[/bold cyan]')}")
    console.print("[dim]Choisissez un outil pour chaque couche.[/dim]\n")

    business = _ask_text("Besoin métier (ex: Analyse les ventes par agence)")
    cloud    = _pick("Cloud provider",  _CLOUD_OPTS)
    wh       = _pick("Data warehouse",  _WH_OPTS)
    orch     = _pick("Orchestrateur",   _ORCH_OPTS)
    ingest   = _pick("Ingestion",       _INGEST_OPTS)
    transform= _pick("Transformation",  _TRANSFORM_OPTS)
    storage  = _pick("Storage / Data Lake", _STORAGE_OPTS)
    bi       = _pick("BI / Analytics",  _BI_OPTS)
    deploy   = _pick("Déploiement",     _DEPLOY_OPTS)
    security_level = _pick("Sécurité",  _SECURITY_OPTS)
    budget   = _pick("Budget",          _BUDGET_OPTS)
    volume   = _pick("Volume de données", _VOLUME_OPTS)

    security_map = {
        "simple":     ["jwt"],
        "rbac":       ["RBAC", "jwt"],
        "enterprise": ["RBAC", "RLS", "Vault"],
    }
    region = ""
    if cloud in ("aws", "azure", "gcp"):
        defaults = {"aws": "eu-west-1", "azure": "westeurope", "gcp": "europe-west1"}
        region = _ask_text(f"Région {cloud.upper()}", default=defaults[cloud])

    return ExplicitStack(
        business_request=business,
        cloud_provider=cloud,
        data_warehouse=wh,
        orchestrator=orch,
        ingestion=ingest,
        transformation=transform,
        data_lake=storage if storage != "none" else None,
        bi_tool=bi,
        deployment=deploy,
        security=security_map[security_level],
        budget=budget,
        data_volume=volume,
        region=region or None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODE 2 — Interactive collection
# ─────────────────────────────────────────────────────────────────────────────

_CLOUD_PREF_OPTS = [
    ("none",          "Pas de préférence — les agents choisissent"),
    ("local-docker",  "Local Docker — machine locale"),
    ("aws",           "AWS"),
    ("azure",         "Azure"),
    ("gcp",           "GCP"),
    ("kubernetes",    "Kubernetes existant"),
    ("ovhcloud",      "OVHcloud"),
    ("scaleway",      "Scaleway"),
    ("on-premise",    "On-premise"),
]
_SECURITY_LEVEL_OPTS = [
    ("simple",     "Simple — login/password, SSL, .env secrets"),
    ("rbac",       "RBAC — rôles et permissions, JWT"),
    ("enterprise", "Enterprise — SSO/OIDC, Vault, audit logs, RLS"),
]
_TEAM_OPTS = [
    ("solo",   "Solo — 1 personne"),
    ("small",  "Petite équipe — 2 à 5 personnes"),
    ("medium", "Équipe moyenne — 6 à 15 personnes"),
    ("large",  "Grande équipe — 15+ personnes"),
]
_MODE_OPTS = [
    ("batch",    "Batch — pipelines planifiés (quotidien, horaire)"),
    ("realtime", "Temps réel — latence < 1 minute"),
    ("both",     "Les deux — batch + streaming"),
]
_DEPLOY_PREF_OPTS = [
    (None,            "Pas de préférence — les agents choisissent"),
    ("docker-compose","Docker Compose — simple, 1 serveur"),
    ("kubernetes",    "Kubernetes — scalable, production"),
    ("managed",       "Services managés cloud — zéro ops"),
]
_COMPLIANCE_OPTS = [
    ("none",    "Aucune exigence spécifique"),
    ("rgpd",    "RGPD (données personnelles EU)"),
    ("hds",     "HDS (données de santé France)"),
    ("hipaa",   "HIPAA (données de santé US)"),
    ("sox",     "SOX (données financières)"),
    ("pci-dss", "PCI-DSS (données de paiement)"),
]


def _interactive_mode2() -> RecommendationContext:
    console.print(f"\n{Rule('[bold cyan]Mode 2 — Recommandation[/bold cyan]')}")
    console.print(
        "[dim]Décrivez votre contexte. Les agents proposeront les meilleures architectures.[/dim]\n"
    )

    business    = _ask_text("Besoin métier (ex: Analyse les données hospitalières)")
    budget      = _pick("Budget",             _BUDGET_OPTS)
    volume      = _pick("Volume de données",  _VOLUME_OPTS)
    security    = _pick("Niveau de sécurité", _SECURITY_LEVEL_OPTS)
    team        = _pick("Taille de l'équipe", _TEAM_OPTS)
    mode        = _pick("Mode de traitement", _MODE_OPTS)
    cloud_pref  = _pick("Cloud préféré",      _CLOUD_PREF_OPTS)
    deploy_pref_raw = _pick("Préférence déploiement", _DEPLOY_PREF_OPTS)
    deploy_pref = None if deploy_pref_raw == "None" else deploy_pref_raw or None
    compliance_raw = _pick("Conformité réglementaire", _COMPLIANCE_OPTS)
    compliance = [] if compliance_raw == "none" else [compliance_raw.upper()]

    open_source_raw = console.input(
        "\n  [bold yellow]Exclure les outils SaaS payants ?[/bold yellow] [dim](o/N)[/dim] : "
    ).strip().lower()
    open_source = open_source_raw in ("o", "oui", "y", "yes")

    existing_raw = _ask_text(
        "Outils déjà en place (séparés par virgule, ou Entrée pour aucun)", default=""
    )
    existing = [t.strip() for t in existing_raw.split(",") if t.strip()] if existing_raw else []

    return RecommendationContext(
        business_request=business,
        budget=budget,
        data_volume=volume,
        security_level=security,
        team_size=team,
        processing_mode=mode,
        cloud_preference=cloud_pref,
        deployment_preference=deploy_pref,
        must_be_open_source=open_source,
        existing_tools=existing,
        compliance_requirements=compliance,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Programmatic runners
# ─────────────────────────────────────────────────────────────────────────────

def run_explicit(
    stack: ExplicitStack,
    output_dir: str | None = "./datasphere-artifacts",
    verbose: bool = True,
) -> OrchestratorOutput:
    """MODE 1 — validate + generate directly from an explicit stack."""
    from datasphere.models.request import BusinessRequest
    from datasphere.models.conversation import ArchitectureProposal
    from datasphere.agents.orchestrator import _step5_generate

    if verbose:
        _print_mode1_summary(stack)

    proposal = ArchitectureProposal(
        id=1,
        name="Stack Explicite",
        tagline="Architecture définie par l'humain",
        constraints=stack.to_architecture_constraints(),
        pros=["Contrôle total — chaque outil choisi explicitement"],
        cons=[],
        estimated_monthly_usd=0.0,
        complexity="medium",
        time_to_deploy="",
        best_for="",
    )
    return _step5_generate(stack.business_request, proposal, output_dir)


def run_recommended(
    ctx: RecommendationContext,
    output_dir: str | None = "./datasphere-artifacts",
    verbose: bool = True,
) -> OrchestratorOutput:
    """MODE 2 — propose 3 architectures, optionally let human choose, generate."""
    from datasphere.agents.proposer import generate_proposals, _apply_team_scoring
    from datasphere.agents.orchestrator import (
        _step3_display_proposals, _step4_choose_proposal, _step5_generate
    )

    raw = ctx.to_raw_constraints()
    proposals = generate_proposals(raw)
    proposals = _apply_team_scoring(proposals, ctx)

    if verbose:
        _print_mode2_context(ctx)
        _step3_display_proposals(proposals)
        chosen = _step4_choose_proposal(proposals)
    else:
        chosen = proposals[0]

    return _step5_generate(ctx.business_request, chosen, output_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_mode1_summary(stack: ExplicitStack) -> None:
    console.print(f"\n{Rule('[bold cyan]Mode 1 — Stack Explicite validée[/bold cyan]')}")
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Couche", style="dim", min_width=18)
    t.add_column("Outil",  style="bold magenta")
    t.add_row("Cloud",          stack.cloud_provider)
    t.add_row("Warehouse",      stack.data_warehouse)
    t.add_row("Orchestration",  stack.orchestrator)
    t.add_row("Ingestion",      stack.ingestion)
    t.add_row("Transformation", stack.transformation)
    t.add_row("Storage",        stack.data_lake or "—")
    t.add_row("BI",             stack.bi_tool)
    t.add_row("Déploiement",    stack.deployment)
    t.add_row("Budget",         stack.budget)
    t.add_row("Volume",         stack.data_volume)
    console.print(t)
    console.print(
        "[dim]Les agents vont valider la compatibilité et générer "
        "toute l'infrastructure.[/dim]\n"
    )


def _print_mode2_context(ctx: RecommendationContext) -> None:
    console.print(f"\n{Rule('[bold cyan]Mode 2 — Contexte analysé[/bold cyan]')}")
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Paramètre", style="dim", min_width=22)
    t.add_column("Valeur",    style="bold yellow")
    t.add_row("Besoin",         ctx.business_request[:60] + ("…" if len(ctx.business_request) > 60 else ""))
    t.add_row("Budget",         ctx.budget)
    t.add_row("Volume",         ctx.data_volume)
    t.add_row("Sécurité",       ctx.security_level)
    t.add_row("Équipe",         ctx.team_size)
    t.add_row("Mode",           ctx.processing_mode)
    t.add_row("Cloud préféré",  ctx.cloud_preference)
    if ctx.must_be_open_source:
        t.add_row("Contrainte",  "[green]Open-source uniquement[/green]")
    if ctx.existing_tools:
        t.add_row("Outils existants", ", ".join(ctx.existing_tools))
    if ctx.compliance_requirements:
        t.add_row("Conformité", ", ".join(ctx.compliance_requirements))
    console.print(t)
    console.print("[dim]Le Stack Advisor génère les architectures optimales…[/dim]\n")
