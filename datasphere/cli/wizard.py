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
    "cloud": "Cloud Provider",
    "warehouse": "Data Warehouse",
    "orchestration": "Orchestration",
    "ingestion": "Ingestion",
    "transformation": "Transformation",
    "storage": "Storage / Data Lake",
    "bi": "BI / Analytics",
    "quality": "Data Quality",
    "catalog": "Data Catalog / Governance",
    "ai": "AI / LLM",
    "vector": "Vector Database",
    "infrastructure": "Infrastructure",
    "monitoring": "Monitoring",
    "security": "Security",
}


def prompt_choice(category: str, options: list[str], default: str) -> str:
    console.print(f"\n[bold cyan]{CATEGORY_LABELS[category]}[/bold cyan]")
    for i, opt in enumerate(options, 1):
        marker = " [green](default)[/green]" if opt == default else ""
        console.print(f"  {i:2}. {opt}{marker}")
    while True:
        raw = console.input(f"  Choose [1-{len(options)}] (Enter for default): ").strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        console.print("  [red]Invalid choice, try again.[/red]")


@click.group()
def main():
    """DataSphere -- stack-agnostic autonomous data platform."""


@main.command()
@click.option("--output", "-o", default="stack.yaml", help="Output file path")
def wizard(output: str):
    """Interactively configure your DataSphere stack."""
    console.print(Panel.fit(
        "[bold green]DataSphere Stack Wizard[/bold green]\n"
        "Configure your stack across 14 layers.\n"
        "Press Enter to keep the default value.",
        border_style="green",
    ))

    name = console.input("\n[bold]Platform name[/bold] (default: my-datasphere): ").strip() or "my-datasphere"
    environment = console.input("[bold]Environment[/bold] (development/staging/production, default: development): ").strip() or "development"

    choices: dict[str, dict] = {}
    for category, options in ALLOWED.items():
        chosen = prompt_choice(category, options, options[0])
        choices[category] = {"type": chosen} if category not in ("cloud", "infrastructure") else {"provider" if category == "cloud" else "type": chosen}

    cfg = StackConfig(name=name, environment=environment, **choices)

    out = Path(output)
    out.write_text(cfg.to_yaml())
    console.print(f"\n[bold green]Stack configuration written to {out}[/bold green]")

    errors = cfg.validate()
    if errors:
        console.print("\n[bold red]Validation warnings:[/bold red]")
        for e in errors:
            console.print(f"  * {e}")
    else:
        console.print("[green]Configuration is valid.[/green]")


@main.command()
@click.argument("stack_file", default="stack.yaml")
def validate(stack_file: str):
    """Validate a stack.yaml configuration."""
    try:
        cfg = StackConfig.from_file(stack_file)
        errors = cfg.validate()
        if errors:
            console.print("[bold red]Validation errors:[/bold red]")
            for e in errors:
                console.print(f"  * {e}")
            sys.exit(1)
        else:
            console.print(f"[bold green]{stack_file} is valid.[/bold green]")
    except FileNotFoundError:
        console.print(f"[red]File not found: {stack_file}[/red]")
        sys.exit(1)


@main.command()
@click.argument("stack_file", default="stack.yaml")
def status(stack_file: str):
    """Show status of all configured services."""
    cfg = StackConfig.from_file(stack_file)
    from datasphere.core.registry import registry

    table = Table(title="DataSphere Stack Status")
    table.add_column("Category", style="cyan")
    table.add_column("Tool", style="magenta")
    table.add_column("Status", style="green")

    for category in ALLOWED:
        cfg_dict = getattr(cfg, category, {})
        tool = cfg_dict.get("type") or cfg_dict.get("provider", "")
        try:
            adapter_cls = registry.get(category, tool)
            from datasphere.adapters.base import AdapterConfig
            adapter = adapter_cls(AdapterConfig(
                host=cfg_dict.get("host", "localhost"),
                port=cfg_dict.get("port", 0),
                username=cfg_dict.get("username", ""),
                password=cfg_dict.get("password", ""),
                database=cfg_dict.get("database", ""),
                extra={k: v for k, v in cfg_dict.items() if k not in ("type", "host", "port", "username", "password", "database")},
            ))
            result = adapter.status()
            s = result.get("status", "unknown")
            color = "green" if s == "healthy" else "yellow" if s in ("managed-saas", "available") else "red"
            table.add_row(category, tool, f"[{color}]{s}[/{color}]")
        except KeyError:
            table.add_row(category, tool, "[yellow]no adapter[/yellow]")

    console.print(table)


if __name__ == "__main__":
    main()
