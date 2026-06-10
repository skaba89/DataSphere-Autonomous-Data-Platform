"""
Stack Discovery Agent — asks 10 context questions, then recommends and generates stack.yaml.
Never imposes a stack. Always derives it from human answers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Discovery questions
# ---------------------------------------------------------------------------

@dataclass
class Answer:
    cloud: str = ""           # local | aws | azure | gcp | ovhcloud | scaleway | on-premise | kubernetes
    source_db: str = ""       # postgresql | mysql | mongodb | oracle | sqlserver | api | files | kafka | other
    warehouse: str = ""       # postgresql | bigquery | snowflake | redshift | synapse | databricks | clickhouse | duckdb
    bi_tool: str = ""         # superset | metabase | grafana | powerbi | tableau | evidence | redash
    orchestrator: str = ""    # airflow | dagster | prefect | argo | kestra | none
    mode: str = ""            # batch | realtime | both
    data_lake: str = ""       # yes | no
    infra: str = ""           # kubernetes | docker | managed
    security: str = ""        # simple | enterprise
    budget: str = ""          # low | medium | enterprise


QUESTIONS = [
    {
        "key": "cloud",
        "text": "☁️  Quel cloud provider (ou infrastructure) ciblez-vous ?",
        "options": [
            ("local",       "Local — Docker sur ma machine"),
            ("aws",         "AWS — Amazon Web Services"),
            ("azure",       "Azure — Microsoft Azure"),
            ("gcp",         "GCP — Google Cloud Platform"),
            ("ovhcloud",    "OVHcloud"),
            ("scaleway",    "Scaleway"),
            ("on-premise",  "On-premise — serveurs internes"),
            ("kubernetes",  "Kubernetes existant (peu importe le cloud)"),
        ],
    },
    {
        "key": "source_db",
        "text": "🗃️  Quelle est la nature principale de vos sources de données ?",
        "options": [
            ("postgresql",  "PostgreSQL / MySQL / MariaDB (bases relationnelles)"),
            ("oracle",      "Oracle / SQL Server (bases enterprise)"),
            ("mongodb",     "MongoDB / NoSQL"),
            ("api",         "APIs REST / webhooks"),
            ("files",       "Fichiers — CSV, Parquet, JSON, Excel"),
            ("kafka",       "Kafka / événements temps réel"),
            ("saas",        "SaaS — Salesforce, HubSpot, Stripe, Google Ads…"),
            ("other",       "Mixte / autre"),
        ],
    },
    {
        "key": "warehouse",
        "text": "🗄️  Quel data warehouse cible souhaitez-vous ?",
        "options": [
            ("auto",        "Recommande-moi le meilleur selon mes choix"),
            ("postgresql",  "PostgreSQL — simple, open-source, auto-hébergé"),
            ("bigquery",    "BigQuery — serverless GCP"),
            ("snowflake",   "Snowflake — multi-cloud SaaS"),
            ("redshift",    "Redshift — AWS natif"),
            ("synapse",     "Azure Synapse — Azure natif"),
            ("databricks",  "Databricks — lakehouse multi-cloud"),
            ("clickhouse",  "ClickHouse — OLAP ultra-rapide"),
            ("duckdb",      "DuckDB — embarqué, idéal pour petits volumes"),
        ],
    },
    {
        "key": "bi_tool",
        "text": "📊  Quel outil BI / visualisation voulez-vous ?",
        "options": [
            ("auto",        "Recommande-moi selon mes choix"),
            ("superset",    "Apache Superset — open-source, puissant"),
            ("metabase",    "Metabase — simple, accessible aux non-techs"),
            ("grafana",     "Grafana — idéal pour métriques / time-series"),
            ("powerbi",     "Power BI — écosystème Microsoft"),
            ("tableau",     "Tableau — standard enterprise"),
            ("evidence",    "Evidence.dev — BI as code"),
            ("redash",      "Redash — SQL-first, léger"),
        ],
    },
    {
        "key": "orchestrator",
        "text": "🎼  Quel orchestrateur de pipelines souhaitez-vous ?",
        "options": [
            ("auto",        "Recommande-moi selon mes choix"),
            ("airflow",     "Apache Airflow — le plus répandu"),
            ("dagster",     "Dagster — asset-based, excellente DX"),
            ("prefect",     "Prefect — cloud-native, Python-first"),
            ("argo",        "Argo Workflows — natif Kubernetes"),
            ("kestra",      "Kestra — YAML-first, low-code"),
            ("none",        "Pas d'orchestration pour l'instant"),
        ],
    },
    {
        "key": "mode",
        "text": "⚡  Quel mode de traitement des données ?",
        "options": [
            ("batch",       "Batch — pipelines planifiés (quotidien, horaire…)"),
            ("realtime",    "Temps réel — streaming, latence < 1 min"),
            ("both",        "Les deux — batch + streaming"),
        ],
    },
    {
        "key": "data_lake",
        "text": "💾  Avez-vous besoin d'un Data Lake (stockage brut des données) ?",
        "options": [
            ("yes",         "Oui — je veux garder les données brutes (S3, MinIO, GCS…)"),
            ("no",          "Non — direct vers le warehouse suffit"),
            ("maybe",       "Je ne sais pas encore"),
        ],
    },
    {
        "key": "infra",
        "text": "🏗️  Comment souhaitez-vous déployer ?",
        "options": [
            ("docker",      "Docker Compose — simple, local ou 1 serveur"),
            ("kubernetes",  "Kubernetes — scalable, production-grade"),
            ("managed",     "Services managés cloud — pas d'infra à gérer"),
        ],
    },
    {
        "key": "security",
        "text": "🔐  Quel niveau de sécurité / authentification ?",
        "options": [
            ("simple",      "Simple — login/password, SSL, secrets en .env"),
            ("enterprise",  "Enterprise — SSO, OIDC, RBAC, Vault, audit logs"),
        ],
    },
    {
        "key": "budget",
        "text": "💶  Quel budget / niveau de complexité acceptable ?",
        "options": [
            ("low",         "Faible — open-source uniquement, zéro licence"),
            ("medium",      "Moyen — quelques SaaS OK si justifiés"),
            ("enterprise",  "Enterprise — budget disponible, priorité à la robustesse"),
        ],
    },
]


# ---------------------------------------------------------------------------
# Stack recommendation engine
# ---------------------------------------------------------------------------

def recommend_stack(a: Answer) -> dict[str, Any]:
    """Derive the best stack from answers. Never hardcodes a single path."""

    stack: dict[str, Any] = {}

    # --- Cloud ---
    cloud_map = {
        "local": "local-docker", "aws": "aws", "azure": "azure",
        "gcp": "gcp", "ovhcloud": "ovhcloud", "scaleway": "scaleway",
        "on-premise": "on-premise", "kubernetes": "kubernetes",
    }
    stack["cloud"] = {"provider": cloud_map.get(a.cloud, "local-docker")}

    # --- Warehouse (auto-recommend if not specified) ---
    if a.warehouse == "auto":
        if a.cloud == "gcp":
            wh = "bigquery"
        elif a.cloud == "aws":
            wh = "redshift"
        elif a.cloud == "azure":
            wh = "azure-synapse"
        elif a.budget == "low" and a.infra == "docker":
            wh = "postgresql"
        elif a.mode == "realtime":
            wh = "clickhouse"
        elif a.budget == "enterprise":
            wh = "snowflake"
        else:
            wh = "postgresql"
    else:
        wh_map = {
            "postgresql": "postgresql", "bigquery": "bigquery",
            "snowflake": "snowflake", "redshift": "redshift",
            "synapse": "azure-synapse", "databricks": "databricks",
            "clickhouse": "clickhouse", "duckdb": "duckdb",
        }
        wh = wh_map.get(a.warehouse, "postgresql")
    stack["warehouse"] = {"type": wh}

    # --- Ingestion ---
    if a.source_db == "kafka" or a.mode == "realtime":
        ingestion = "kafka-connect" if a.mode == "realtime" else "debezium"
    elif a.source_db == "saas":
        ingestion = "airbyte"
    elif a.budget == "low":
        ingestion = "meltano"
    else:
        ingestion = "airbyte"
    stack["ingestion"] = {"type": ingestion}

    # --- Transformation ---
    if a.mode == "realtime":
        transformation = "flink"
    elif a.warehouse in ("databricks",):
        transformation = "spark"
    else:
        transformation = "dbt"
    stack["transformation"] = {"type": transformation}

    # --- Orchestration (auto-recommend) ---
    if a.orchestrator == "auto" or a.orchestrator == "":
        if a.infra == "kubernetes":
            orch = "argo"
        elif a.mode == "realtime":
            orch = "prefect"
        elif a.budget == "low":
            orch = "airflow"
        else:
            orch = "dagster"
    elif a.orchestrator == "none":
        orch = "airflow"  # still include but mark as optional
    else:
        orch = a.orchestrator
    stack["orchestration"] = {"type": orch}

    # --- Storage / Data Lake ---
    if a.data_lake in ("yes", "maybe"):
        if a.cloud == "aws":
            storage_type = "s3"
        elif a.cloud == "azure":
            storage_type = "adls"
        elif a.cloud == "gcp":
            storage_type = "gcs"
        else:
            storage_type = "minio"
    else:
        storage_type = "minio" if a.infra != "managed" else "s3"
    stack["storage"] = {"type": storage_type}

    # --- BI ---
    if a.bi_tool == "auto" or a.bi_tool == "":
        if a.cloud == "azure" and a.budget == "enterprise":
            bi = "powerbi"
        elif a.mode == "realtime":
            bi = "grafana"
        elif a.budget == "low":
            bi = "metabase"
        else:
            bi = "superset"
    else:
        bi_map = {
            "superset": "superset", "metabase": "metabase", "grafana": "grafana",
            "powerbi": "powerbi", "tableau": "tableau", "evidence": "evidence",
            "redash": "redash",
        }
        bi = bi_map.get(a.bi_tool, "superset")
    stack["bi"] = {"type": bi}

    # --- Quality ---
    if a.transformation == "dbt" or transformation == "dbt":
        quality = "dbt-tests"
    elif a.budget == "enterprise":
        quality = "soda-core"
    else:
        quality = "great-expectations"
    stack["quality"] = {"type": quality}

    # --- Catalog ---
    if a.budget == "low":
        catalog = "marquez"
    elif a.budget == "enterprise":
        catalog = "datahub"
    else:
        catalog = "openmetadata"
    stack["catalog"] = {"type": catalog}

    # --- AI ---
    if a.budget == "low" and a.infra != "managed":
        ai = "ollama"
    elif a.cloud == "azure" and a.budget == "enterprise":
        ai = "azure-openai"
    else:
        ai = "openai"
    stack["ai"] = {"type": ai}

    # --- Vector DB ---
    if wh == "postgresql":
        vector = "pgvector"
    elif a.budget == "low":
        vector = "chroma"
    else:
        vector = "qdrant"
    stack["vector"] = {"type": vector}

    # --- Infrastructure ---
    if a.infra == "kubernetes":
        infra_type = "helm"
    elif a.infra == "managed":
        infra_type = "terraform"
    else:
        infra_type = "docker-compose"
    stack["infrastructure"] = {"type": infra_type}

    # --- Monitoring ---
    if a.infra == "managed" and a.cloud in ("aws", "azure", "gcp"):
        monitoring = "opentelemetry"
    else:
        monitoring = "prometheus"
    stack["monitoring"] = {"type": monitoring}

    # --- Security ---
    if a.security == "enterprise":
        security = "keycloak"
    else:
        security = "vault"
    stack["security"] = {"type": security}

    return stack


def explain_choices(a: Answer, stack: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (layer, tool, reason) for each recommendation."""
    reasons = []

    wh = stack["warehouse"]["type"]
    reasons.append(("Warehouse", wh, _wh_reason(a, wh)))
    reasons.append(("Ingestion", stack["ingestion"]["type"], _ingestion_reason(a)))
    reasons.append(("Transformation", stack["transformation"]["type"], _transform_reason(a)))
    reasons.append(("Orchestration", stack["orchestration"]["type"], _orch_reason(a)))
    reasons.append(("Storage", stack["storage"]["type"], _storage_reason(a)))
    reasons.append(("BI", stack["bi"]["type"], _bi_reason(a)))
    reasons.append(("Qualité", stack["quality"]["type"], _quality_reason(a)))
    reasons.append(("Catalog", stack["catalog"]["type"], _catalog_reason(a)))
    reasons.append(("AI/LLM", stack["ai"]["type"], _ai_reason(a)))
    reasons.append(("Vector DB", stack["vector"]["type"], _vector_reason(a, wh)))
    reasons.append(("Infra", stack["infrastructure"]["type"], _infra_reason(a)))
    reasons.append(("Monitoring", stack["monitoring"]["type"], _monitoring_reason(a)))
    reasons.append(("Sécurité", stack["security"]["type"], _security_reason(a)))

    return reasons


def _wh_reason(a: Answer, wh: str) -> str:
    if a.warehouse != "auto":
        return "Choix explicite de l'humain"
    if wh == "bigquery":
        return "Cloud GCP → BigQuery est natif et serverless"
    if wh == "redshift":
        return "Cloud AWS → Redshift intégré nativement"
    if wh == "azure-synapse":
        return "Cloud Azure → Synapse est l'offre native"
    if wh == "clickhouse":
        return "Mode temps réel → ClickHouse excelle en OLAP haute fréquence"
    if wh == "snowflake":
        return "Budget enterprise → Snowflake offre séparation compute/storage"
    return "Budget faible + Docker → PostgreSQL, open-source, zéro coût"


def _ingestion_reason(a: Answer) -> str:
    if a.source_db == "kafka" or a.mode == "realtime":
        return "Sources streaming → Kafka Connect / Debezium natifs"
    if a.source_db == "saas":
        return "Sources SaaS → Airbyte a 300+ connecteurs"
    if a.budget == "low":
        return "Budget faible → Meltano, open-source, Singer-based"
    return "Airbyte : meilleur rapport connecteurs / maintenabilité"


def _transform_reason(a: Answer) -> str:
    if a.mode == "realtime":
        return "Mode temps réel → Flink est le standard streaming"
    if a.warehouse in ("databricks",):
        return "Databricks → Spark natif"
    return "dbt : standard industrie pour la transformation SQL"


def _orch_reason(a: Answer) -> str:
    if a.orchestrator not in ("auto", "none", ""):
        return "Choix explicite de l'humain"
    if a.infra == "kubernetes":
        return "Kubernetes → Argo Workflows est natif K8s"
    if a.mode == "realtime":
        return "Temps réel → Prefect gère bien les flows événementiels"
    if a.budget == "low":
        return "Budget faible → Airflow, mature, open-source"
    return "Dagster : asset-based, meilleure observabilité que Airflow"


def _storage_reason(a: Answer) -> str:
    if a.data_lake == "no":
        return "Pas de data lake demandé — storage minimal"
    if a.cloud == "aws":
        return "AWS → S3 est le stockage natif"
    if a.cloud == "azure":
        return "Azure → ADLS Gen2 optimisé pour l'analytique"
    if a.cloud == "gcp":
        return "GCP → GCS natif et intégré à BigQuery"
    return "Self-hosted → MinIO, compatible S3, open-source"


def _bi_reason(a: Answer) -> str:
    if a.bi_tool not in ("auto", ""):
        return "Choix explicite de l'humain"
    if a.cloud == "azure" and a.budget == "enterprise":
        return "Azure enterprise → Power BI intégré à l'écosystème Microsoft"
    if a.mode == "realtime":
        return "Temps réel → Grafana excelle pour les métriques live"
    if a.budget == "low":
        return "Budget faible → Metabase, simple et accessible"
    return "Superset : le BI open-source le plus complet"


def _quality_reason(a: Answer) -> str:
    if a.budget == "enterprise":
        return "Budget enterprise → Soda Core avec checks YAML stricts"
    return "dbt tests intégrés → zéro outil supplémentaire"


def _catalog_reason(a: Answer) -> str:
    if a.budget == "low":
        return "Budget faible → Marquez (OpenLineage), léger"
    if a.budget == "enterprise":
        return "Enterprise → DataHub, standard LinkedIn / industrie"
    return "OpenMetadata : le plus complet en open-source"


def _ai_reason(a: Answer) -> str:
    if a.budget == "low" and a.infra != "managed":
        return "Budget faible → Ollama fait tourner des LLMs en local"
    if a.cloud == "azure" and a.budget == "enterprise":
        return "Azure enterprise → Azure OpenAI pour conformité et SLA"
    return "OpenAI : API la plus mature et documentée"


def _vector_reason(a: Answer, wh: str) -> str:
    if wh == "postgresql":
        return "PostgreSQL déjà présent → pgvector évite un service supplémentaire"
    if a.budget == "low":
        return "Budget faible → Chroma, léger et embarqué"
    return "Qdrant : performant, Rust-based, production-ready"


def _infra_reason(a: Answer) -> str:
    if a.infra == "kubernetes":
        return "Kubernetes demandé → Helm charts pour déploiement reproductible"
    if a.infra == "managed":
        return "Services managés → Terraform pour provisioning IaC"
    return "Docker Compose : simple, idéal pour 1 serveur ou local"


def _monitoring_reason(a: Answer) -> str:
    if a.infra == "managed" and a.cloud in ("aws", "azure", "gcp"):
        return "Cloud managé → OpenTelemetry s'intègre aux outils cloud natifs"
    return "Prometheus + Grafana : standard open-source le plus répandu"


def _security_reason(a: Answer) -> str:
    if a.security == "enterprise":
        return "Enterprise → Keycloak : SSO, OIDC, RBAC, intégration LDAP/AD"
    return "Simple → Vault suffit pour la gestion des secrets"


# ---------------------------------------------------------------------------
# Interactive discovery flow
# ---------------------------------------------------------------------------

def run_discovery() -> tuple[Answer, dict[str, Any]]:
    console.print(Panel.fit(
        "[bold green]DataSphere — Agent de Découverte de Stack[/bold green]\n"
        "[dim]Je vais vous poser 10 questions pour recommander\n"
        "la stack optimale pour votre contexte.[/dim]",
        border_style="green",
        padding=(1, 4),
    ))

    answer = Answer()

    for q in QUESTIONS:
        console.print(f"\n[bold yellow]{q['text']}[/bold yellow]")
        options = q["options"]
        for i, (_, label) in enumerate(options, 1):
            console.print(f"  [cyan]{i:2}.[/cyan] {label}")

        while True:
            raw = console.input(f"\n  Votre choix [1-{len(options)}] : ").strip()
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    setattr(answer, q["key"], options[idx][0])
                    break
            except ValueError:
                pass
            console.print("  [red]Saisie invalide, réessayez.[/red]")

    return answer, recommend_stack(answer)


def display_recommendation(answer: Answer, stack: dict[str, Any]) -> None:
    console.print(f"\n{Rule('[bold green]Stack recommandée[/bold green]')}")

    reasons = explain_choices(answer, stack)
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Couche", style="cyan", min_width=14)
    table.add_column("Outil recommandé", style="bold magenta", min_width=18)
    table.add_column("Pourquoi", style="dim")

    for layer, tool, reason in reasons:
        table.add_row(layer, tool, reason)

    console.print(table)


def confirm_or_adjust(stack: dict[str, Any]) -> dict[str, Any]:
    """Let the human override any recommendation before writing stack.yaml."""
    from datasphere.core.config import ALLOWED

    console.print(f"\n{Rule('[bold yellow]Ajustements manuels (optionnel)[/bold yellow]')}")
    console.print("[dim]Appuyez sur Entrée pour accepter toutes les recommandations.[/dim]")
    console.print("[dim]Ou entrez le numéro d'une couche pour la modifier.\n[/dim]")

    layers = list(stack.keys())
    layer_labels = {
        "cloud": "Cloud", "warehouse": "Warehouse", "ingestion": "Ingestion",
        "transformation": "Transformation", "orchestration": "Orchestration",
        "storage": "Storage", "bi": "BI", "quality": "Qualité",
        "catalog": "Catalog", "ai": "AI/LLM", "vector": "Vector DB",
        "infrastructure": "Infrastructure", "monitoring": "Monitoring",
        "security": "Sécurité",
    }

    for i, layer in enumerate(layers, 1):
        tool = stack[layer].get("type") or stack[layer].get("provider", "")
        console.print(f"  [cyan]{i:2}.[/cyan] {layer_labels.get(layer, layer):16} → [magenta]{tool}[/magenta]")

    while True:
        raw = console.input("\n  Numéro à modifier (ou Entrée pour valider) : ").strip()
        if not raw:
            break
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(layers):
                layer = layers[idx]
                options = ALLOWED.get(layer, [])
                console.print(f"\n  Options pour [cyan]{layer}[/cyan] :")
                for j, opt in enumerate(options, 1):
                    console.print(f"    {j}. {opt}")
                choice_raw = console.input(f"  Nouveau choix [1-{len(options)}] : ").strip()
                try:
                    cidx = int(choice_raw) - 1
                    if 0 <= cidx < len(options):
                        key = "provider" if layer == "cloud" else "type"
                        stack[layer] = {key: options[cidx]}
                        console.print(f"  [green]✓ {layer} → {options[cidx]}[/green]")
                except (ValueError, IndexError):
                    console.print("  [red]Choix invalide.[/red]")
        except (ValueError, IndexError):
            console.print("  [red]Numéro invalide.[/red]")

    return stack
