"""
Dialogue Agent — étape 2 du flow conversationnel.

Pose les questions techniques à l'humain après qu'il a exprimé son besoin métier.
Ne suppose rien. Chaque question est contextualisée par les réponses précédentes.
"""
from __future__ import annotations
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()

CLOUD_OPTIONS = [
    ("local-docker",  "Local Docker — machine locale ou serveur unique"),
    ("aws",           "AWS — Amazon Web Services"),
    ("azure",         "Azure — Microsoft Azure"),
    ("gcp",           "GCP — Google Cloud Platform"),
    ("kubernetes",    "Kubernetes existant (cloud agnostic)"),
    ("ovhcloud",      "OVHcloud"),
    ("scaleway",      "Scaleway"),
    ("on-premise",    "On-premise — datacenter interne"),
]

BUDGET_OPTIONS = [
    ("low",        "Faible — open-source uniquement, zéro licence SaaS"),
    ("medium",     "Moyen — quelques SaaS OK si bien justifiés"),
    ("enterprise", "Enterprise — budget disponible, priorité robustesse"),
]

VOLUME_OPTIONS = [
    ("small",  "Small  — < 10 Go/jour, quelques milliers de lignes"),
    ("medium", "Medium — 10 Go–1 To/jour, millions de lignes"),
    ("large",  "Large  — 1–10 To/jour, dizaines de millions de lignes"),
    ("xlarge", "XLarge — > 10 To/jour, streaming ou centaines de millions/jour"),
]

MODE_OPTIONS = [
    ("batch",    "Batch — pipelines planifiés (quotidien, horaire)"),
    ("realtime", "Temps réel — latence < 1 minute, streaming"),
    ("both",     "Les deux — batch + streaming"),
]

SECURITY_OPTIONS = [
    ("simple",     "Simple — login/password, .env secrets, SSL"),
    ("rbac",       "RBAC — contrôle d'accès par rôle, sans SSO"),
    ("enterprise", "Enterprise — SSO/OIDC, Vault, RBAC, RLS, audit logs"),
]

DEPLOYMENT_OPTIONS = [
    ("docker-compose", "Docker Compose — simple, idéal pour 1 serveur ou local"),
    ("kubernetes",     "Kubernetes — scalable, production-grade"),
    ("managed",        "Services managés cloud — pas d'infra à gérer"),
]


def _ask(prompt: str, options: list[tuple[str, str]], allow_skip: bool = False) -> str:
    console.print(f"\n[bold yellow]{prompt}[/bold yellow]")
    for i, (_, label) in enumerate(options, 1):
        console.print(f"  [cyan]{i:2}.[/cyan]  {label}")
    if allow_skip:
        console.print(f"  [dim] 0.  Pas de préférence — laissez l'agent choisir[/dim]")

    while True:
        raw = console.input(f"\n  Votre choix [1-{len(options)}]{' ou 0' if allow_skip else ''} : ").strip()
        if allow_skip and raw == "0":
            return "auto"
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        console.print("  [red]Choix invalide, réessayez.[/red]")


def _ask_text(prompt: str, default: str = "") -> str:
    suffix = f" [dim](défaut: {default})[/dim]" if default else ""
    raw = console.input(f"\n[bold yellow]{prompt}[/bold yellow]{suffix} : ").strip()
    return raw or default


def collect_constraints(business_request: str) -> dict:
    """
    Étape 2 — pose les questions techniques contextualisées.
    Retourne un dict compatible avec ArchitectureConstraints.
    """
    console.print(f"\n{Rule('[bold cyan]Étape 2 — Contraintes techniques[/bold cyan]')}")
    console.print(
        f"[dim]Besoin métier : \"{business_request}\"[/dim]\n"
        "[dim]Je vais vous poser quelques questions pour proposer les meilleures architectures.[/dim]"
    )

    cloud = _ask("Quel cloud provider ou infrastructure ciblez-vous ?", CLOUD_OPTIONS)
    budget = _ask("Quel budget / niveau de complexité acceptable ?", BUDGET_OPTIONS)
    volume = _ask("Quel volume de données attendu ?", VOLUME_OPTIONS)
    mode = _ask("Quel mode de traitement des données ?", MODE_OPTIONS)
    security_level = _ask("Quel niveau de sécurité requis ?", SECURITY_OPTIONS)
    deployment = _ask("Comment souhaitez-vous déployer ?", DEPLOYMENT_OPTIONS)

    # Derive security controls from level
    security = {
        "simple":     ["jwt"],
        "rbac":       ["RBAC", "jwt"],
        "enterprise": ["RBAC", "RLS", "Vault"],
    }[security_level]

    # Derive IaC from deployment
    iac = {
        "docker-compose": "docker-compose",
        "kubernetes":     "helm",
        "managed":        "terraform",
    }[deployment]

    # Optional: region
    region = ""
    if cloud in ("aws", "azure", "gcp"):
        region = _ask_text(
            f"Région {cloud.upper()} souhaitée",
            default={"aws": "eu-west-1", "azure": "westeurope", "gcp": "europe-west1"}[cloud]
        )

    return {
        "cloud_provider":  cloud,
        "budget":          budget,
        "data_volume":     volume,
        "processing_mode": mode,
        "security":        security,
        "deployment":      deployment,
        "iac":             iac,
        "region":          region or None,
        # These will be filled by StackAdvisor proposals
        "data_warehouse":  "auto",
        "orchestrator":    "auto",
        "ingestion":       "auto",
        "transformation":  "auto",
        "data_lake":       "auto",
        "bi_tool":         "auto",
        "catalog":         "auto",
        "quality":         "auto",
    }
