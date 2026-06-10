"""
DataSphere CLI — stack-agnostic autonomous data platform.

Usage:
  datasphere wizard            # Guided discovery (recommended)
  datasphere wizard --expert   # Direct tool selection
  datasphere validate          # Validate stack.yaml
  datasphere status            # Check service health
"""
from __future__ import annotations
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datasphere.core.config import ALLOWED, StackConfig

console = Console()

CATEGORY_LABELS = {
    "cloud":          "Cloud Provider",
    "warehouse":      "Data Warehouse",
    "orchestration":  "Orchestration",
    "ingestion":      "Ingestion",
    "transformation": "Transformation",
    "storage":        "Storage / Data Lake",
    "bi":             "BI / Analytics",
    "quality":        "Data Quality",
    "catalog":        "Data Catalog",
    "ai":             "AI / LLM",
    "vector":         "Vector Database",
    "infrastructure": "Infrastructure",
    "monitoring":     "Monitoring",
    "security":       "Security",
}


def prompt_choice(category: str, options: list[str], default: str) -> str:
    console.print(f"\n[bold cyan]{CATEGORY_LABELS[category]}[/bold cyan]")
    for i, opt in enumerate(options, 1):
        marker = " [green](défaut)[/green]" if opt == default else ""
        console.print(f"  {i:2}. {opt}{marker}")
    while True:
        raw = console.input(f"  Choix [1-{len(options)}] (Entrée = défaut) : ").strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        console.print("  [red]Choix invalide, réessayez.[/red]")


@click.group()
def main():
    """DataSphere — plateforme de données stack-agnostic."""


@main.command()
@click.option("--output", "-o", default="stack.yaml", help="Fichier de sortie")
@click.option("--expert", is_flag=True, default=False, help="Sélection directe des outils (sans discovery)")
def wizard(output: str, expert: bool):
    """Configure votre stack via 10 questions de contexte (ou mode expert)."""
    from datasphere.cli.discovery import run_discovery, display_recommendation, confirm_or_adjust

    if expert:
        console.print(Panel.fit(
            "[bold green]DataSphere — Mode Expert[/bold green]\n"
            "[dim]Sélection directe des outils par couche.[/dim]",
            border_style="cyan",
        ))
        name = console.input("\n[bold]Nom de la plateforme[/bold] (défaut: my-datasphere) : ").strip() or "my-datasphere"
        environment = console.input("[bold]Environnement[/bold] (development/staging/production) : ").strip() or "development"
        stack: dict = {}
        for category, options in ALLOWED.items():
            chosen = prompt_choice(category, options, options[0])
            key = "provider" if category == "cloud" else "type"
            stack[category] = {key: chosen}
    else:
        answer, stack = run_discovery()
        display_recommendation(answer, stack)
        stack = confirm_or_adjust(stack)
        name = console.input("\n[bold]Nom de la plateforme[/bold] (défaut: my-datasphere) : ").strip() or "my-datasphere"
        environment = console.input("[bold]Environnement[/bold] (development/staging/production) : ").strip() or "development"

    cfg = StackConfig(name=name, environment=environment, **stack)
    out = Path(output)
    out.write_text(cfg.to_yaml())
    console.print(f"\n[bold green]✓ Stack écrite dans {out}[/bold green]")

    errors = cfg.validate()
    if errors:
        console.print("\n[bold red]Avertissements :[/bold red]")
        for e in errors:
            console.print(f"  • {e}")
    else:
        console.print("[green]✓ Configuration valide.[/green]")


@main.command()
@click.argument("stack_file", default="stack.yaml")
def validate(stack_file: str):
    """Valide un fichier stack.yaml."""
    try:
        cfg = StackConfig.from_file(stack_file)
        errors = cfg.validate()
        if errors:
            console.print("[bold red]Erreurs de validation :[/bold red]")
            for e in errors:
                console.print(f"  • {e}")
            sys.exit(1)
        else:
            console.print(f"[bold green]✓ {stack_file} est valide.[/bold green]")
    except FileNotFoundError:
        console.print(f"[red]Fichier introuvable : {stack_file}[/red]")
        sys.exit(1)


@main.command()
@click.argument("stack_file", default="stack.yaml")
def status(stack_file: str):
    """Affiche le statut de tous les services configurés."""
    cfg = StackConfig.from_file(stack_file)
    from datasphere.core.registry import registry
    from datasphere.adapters.base import AdapterConfig

    table = Table(title="DataSphere Stack Status")
    table.add_column("Couche", style="cyan")
    table.add_column("Outil", style="magenta")
    table.add_column("Statut", style="green")

    for category in ALLOWED:
        cfg_dict = getattr(cfg, category, {})
        tool = cfg_dict.get("type") or cfg_dict.get("provider", "")
        try:
            adapter_cls = registry.get(category, tool)
            adapter = adapter_cls(AdapterConfig(
                host=cfg_dict.get("host", "localhost"),
                port=cfg_dict.get("port", 0),
                username=cfg_dict.get("username", ""),
                password=cfg_dict.get("password", ""),
                database=cfg_dict.get("database", ""),
                extra={k: v for k, v in cfg_dict.items()
                       if k not in ("type", "provider", "host", "port", "username", "password", "database")},
            ))
            s = adapter.status().get("status", "unknown")
            color = "green" if s == "healthy" else "yellow" if s in ("managed-saas", "available") else "red"
            table.add_row(category, tool, f"[{color}]{s}[/{color}]")
        except KeyError:
            table.add_row(category, tool, "[dim]pas d'adaptateur[/dim]")

    console.print(table)


from datasphere.cli.run_agents import run_agents
main.add_command(run_agents, name="run")


@main.command()
@click.option("--host", default="0.0.0.0", help="Adresse d'écoute")
@click.option("--port", "-p", default=8000, type=int, help="Port")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload (développement)")
@click.option("--workers", default=1, type=int, help="Nombre de workers")
def api(host: str, port: int, reload: bool, workers: int):
    """Lance l'API REST DataSphere (FastAPI + Uvicorn)."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn non installé — pip install datasphere[api][/red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold green]DataSphere API[/bold green]\n"
        f"[dim]http://{host}:{port}  |  docs → http://{host}:{port}/docs[/dim]",
        border_style="green",
    ))
    uvicorn.run(
        "datasphere.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info",
    )


@main.command("dbt-generate")
@click.option("--request", "-r", required=True, help="Besoin métier")
@click.option("--warehouse", "-w", default="snowflake", help="Data warehouse cible")
@click.option("--ingestion", "-i", default="airbyte", help="Outil d'ingestion")
@click.option("--output", "-o", default="./dbt", help="Répertoire de sortie")
def dbt_generate(request: str, warehouse: str, ingestion: str, output: str):
    """Génère un scaffold dbt complet (modèles, tests, profiles)."""
    from datasphere.generators.dbt_project import DbtProjectGenerator
    from datasphere.models.request import ArchitectureConstraints

    constraints = ArchitectureConstraints(
        cloud_provider="aws",
        data_warehouse=warehouse,
        orchestrator="airflow",
        ingestion=ingestion,
        transformation="dbt",
        bi_tool="superset",
        deployment="kubernetes",
        security=["RBAC"],
        budget="medium",
        data_lake=None,
        catalog=None,
        quality=None,
    )
    gen = DbtProjectGenerator()
    project = gen.generate(request, constraints)
    written = project.write(output)

    console.print(f"\n[bold green]✓ Projet dbt généré dans {output}/dbt/[/bold green]")
    console.print(f"  [dim]{len(written)} fichiers créés[/dim]")
    console.print("\n[bold]Démarrage rapide :[/bold]")
    console.print(f"  cd {output}/dbt && pip install dbt-{warehouse.replace('-', '_')} && dbt deps && dbt debug")


@main.command("dag-generate")
@click.option("--request", "-r", required=True, help="Besoin métier")
@click.option("--orchestrator", default="airflow", help="Orchestrateur (airflow)")
@click.option("--ingestion", "-i", default="airbyte", help="Outil d'ingestion")
@click.option("--transformation", "-t", default="dbt", help="Outil de transformation")
@click.option("--warehouse", "-w", default="snowflake", help="Data warehouse")
@click.option("--output", "-o", default="./dags", help="Répertoire de sortie")
def dag_generate(request: str, orchestrator: str, ingestion: str, transformation: str,
                 warehouse: str, output: str):
    """Génère les DAGs Airflow Python pour le pipeline et la qualité."""
    if orchestrator.lower() not in ("airflow",):
        console.print(f"[yellow]DAG generation disponible uniquement pour Airflow (reçu: {orchestrator})[/yellow]")
        return

    from datasphere.generators.airflow_dag import AirflowDagGenerator
    from datasphere.models.request import ArchitectureConstraints

    constraints = ArchitectureConstraints(
        cloud_provider="aws",
        data_warehouse=warehouse,
        orchestrator=orchestrator,
        ingestion=ingestion,
        transformation=transformation,
        bi_tool="superset",
        deployment="kubernetes",
        security=["RBAC"],
        budget="medium",
        data_lake=None,
        catalog=None,
        quality="great-expectations",
    )
    gen = AirflowDagGenerator()
    dags = gen.generate(request, constraints)
    written = dags.write(output)

    console.print(f"\n[bold green]✓ DAGs générés dans {output}/dags/[/bold green]")
    console.print(f"  [dim]{len(written)} fichiers créés[/dim]")
    for path in written:
        if path.endswith(".py"):
            console.print(f"  • {path}")


if __name__ == "__main__":
    main()
