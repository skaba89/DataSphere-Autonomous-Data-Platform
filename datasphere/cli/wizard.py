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


if __name__ == "__main__":
    main()
