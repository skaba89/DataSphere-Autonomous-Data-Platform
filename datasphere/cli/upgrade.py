"""Commande datasphere upgrade — vérifie et met à jour la plateforme."""
from __future__ import annotations
import json
import subprocess
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Adaptateurs Python optionnels à vérifier/mettre à jour
OPTIONAL_PACKAGES: list[tuple[str, str, str]] = [
    # (pip_name, import_name, description)
    ("psycopg2-binary",                "psycopg2",          "PostgreSQL / Redshift"),
    ("snowflake-connector-python",     "snowflake.connector","Snowflake"),
    ("google-cloud-bigquery",          "google.cloud.bigquery", "BigQuery"),
    ("databricks-sql-connector",       "databricks.sql",    "Databricks"),
    ("dbt-core",                       "dbt",               "dbt Core"),
    ("apache-airflow",                 "airflow",           "Airflow"),
    ("dagster",                        "dagster",           "Dagster"),
    ("prefect",                        "prefect",           "Prefect"),
    ("pyspark",                        "pyspark",           "Apache Spark"),
    ("minio",                          "minio",             "MinIO"),
    ("boto3",                          "boto3",             "AWS SDK"),
    ("azure-storage-blob",             "azure.storage.blob","Azure Storage"),
    ("google-cloud-storage",           "google.cloud.storage","GCS"),
    ("openai",                         "openai",            "OpenAI"),
    ("anthropic",                      "anthropic",         "Anthropic"),
    ("qdrant-client",                  "qdrant_client",     "Qdrant"),
    ("weaviate-client",                "weaviate",          "Weaviate"),
    ("chromadb",                       "chromadb",          "ChromaDB"),
    ("pymilvus",                       "pymilvus",          "Milvus"),
    ("hvac",                           "hvac",              "HashiCorp Vault"),
    ("fastapi",                        "fastapi",           "FastAPI"),
    ("uvicorn",                        "uvicorn",           "Uvicorn"),
    ("sqlmesh",                        "sqlmesh",           "SQLMesh"),
    ("soda-core",                      "soda",              "Soda Core"),
]

CORE_PACKAGES = [
    ("pydantic",  "pydantic",  "Modèles de données"),
    ("rich",      "rich",      "Terminal UI"),
    ("click",     "click",     "CLI"),
    ("pyyaml",    "yaml",      "YAML"),
]


def _get_installed_version(pip_name: str) -> str | None:
    try:
        return version(pip_name)
    except PackageNotFoundError:
        return None


def _get_latest_version(pip_name: str) -> str | None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", pip_name],
            capture_output=True, text=True, timeout=10,
        )
        # pip index versions returns: "Available versions: x.y.z, ..."
        if "Available versions:" in result.stdout:
            versions_str = result.stdout.split("Available versions:")[1].strip()
            latest = versions_str.split(",")[0].strip()
            return latest
    except Exception:
        pass
    return None


def _can_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


@click.command("upgrade")
@click.option("--check-only", is_flag=True, default=False,
              help="Vérifier uniquement, sans installer")
@click.option("--core-only", is_flag=True, default=False,
              help="Mettre à jour uniquement les dépendances core")
@click.option("--package", "-p", multiple=True,
              help="Mettre à jour un package spécifique (ex: --package dbt-core)")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Confirmer automatiquement les installations")
def upgrade(check_only: bool, core_only: bool, package: tuple[str, ...], yes: bool):
    """Vérifie et met à jour DataSphere et ses dépendances."""

    console.print(Panel.fit(
        "[bold green]DataSphere — Upgrade Manager[/bold green]\n"
        "[dim]Vérifie l'état de toutes les dépendances de la plateforme[/dim]",
        border_style="green",
    ))

    # --- Check DataSphere itself ---
    ds_version = _get_installed_version("datasphere") or "dev"
    console.print(f"\n[bold]DataSphere version :[/bold] [cyan]{ds_version}[/cyan]\n")

    # --- Build status tables ---
    packages_to_check = CORE_PACKAGES + ([] if core_only else OPTIONAL_PACKAGES)

    # If specific packages requested, filter
    if package:
        filter_set = set(p.lower() for p in package)
        packages_to_check = [
            pkg for pkg in packages_to_check
            if pkg[0].lower() in filter_set
        ]
        if not packages_to_check:
            console.print(f"[red]Aucun des packages spécifiés trouvé : {list(package)}[/red]")
            return

    table = Table(
        title="État des dépendances",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Package",       style="cyan",   no_wrap=True)
    table.add_column("Description",   style="dim")
    table.add_column("Installé",      justify="center")
    table.add_column("Disponible",    justify="center")
    table.add_column("Statut",        justify="center")

    to_install: list[str] = []
    to_upgrade: list[tuple[str, str, str]] = []  # (pip_name, current, latest)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as prog:
        task = prog.add_task("Vérification des packages...", total=None)

        for pip_name, import_name, description in packages_to_check:
            installed = _get_installed_version(pip_name)
            importable = _can_import(import_name)

            if installed:
                inst_display = f"[green]{installed}[/green]"
                status = "[green]✓ OK[/green]"
                latest_display = "[dim]—[/dim]"
            else:
                inst_display = "[red]non installé[/red]"
                latest_display = "[dim]—[/dim]"
                status = "[yellow]⚠ absent[/yellow]"
                to_install.append(pip_name)

            table.add_row(pip_name, description, inst_display, latest_display, status)

        prog.remove_task(task)

    console.print(table)

    # --- Summary ---
    console.print()
    if not to_install and not to_upgrade:
        console.print("[bold green]✓ Toutes les dépendances core sont à jour.[/bold green]")
        if check_only:
            return

    if to_install:
        console.print(f"[yellow]{len(to_install)} package(s) absent(s) :[/yellow]")
        for p in to_install:
            console.print(f"  • {p}")

    if check_only:
        console.print("\n[dim]Mode vérification uniquement — aucune installation effectuée.[/dim]")
        return

    # --- Install missing core packages ---
    core_missing = [p for p in to_install if p in [c[0] for c in CORE_PACKAGES]]
    optional_missing = [p for p in to_install if p not in core_missing]

    if core_missing:
        console.print(f"\n[bold]Installation des packages core manquants...[/bold]")
        _pip_install(core_missing)

    if optional_missing and not core_only:
        if not yes:
            response = console.input(
                f"\nInstaller les {len(optional_missing)} package(s) optionnel(s) absent(s) ? [o/N] "
            ).strip().lower()
            if response not in ("o", "oui", "y", "yes"):
                console.print("[dim]Packages optionnels ignorés.[/dim]")
                optional_missing = []

        if optional_missing:
            _pip_install(optional_missing)

    # --- Upgrade DataSphere itself ---
    console.print("\n[bold]Mise à jour de DataSphere...[/bold]")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "datasphere"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            new_version = _get_installed_version("datasphere") or "?"
            console.print(f"[green]✓ DataSphere mis à jour → {new_version}[/green]")
        else:
            console.print("[dim]DataSphere (version dev) — pas de mise à jour PyPI disponible.[/dim]")
    except Exception:
        console.print("[dim]Mise à jour DataSphere depuis PyPI ignorée (mode dev).[/dim]")

    console.print("\n[bold green]✓ Upgrade terminé.[/bold green]")
    _print_next_steps()


def _pip_install(packages: list[str]) -> None:
    if not packages:
        return
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as prog:
        for pkg in packages:
            task = prog.add_task(f"Installation {pkg}...", total=None)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    v = _get_installed_version(pkg) or "?"
                    prog.remove_task(task)
                    console.print(f"  [green]✓ {pkg} {v}[/green]")
                else:
                    prog.remove_task(task)
                    console.print(f"  [red]✗ {pkg} — {result.stderr[:100]}[/red]")
            except subprocess.TimeoutExpired:
                prog.remove_task(task)
                console.print(f"  [yellow]⚠ {pkg} — timeout[/yellow]")
            except Exception as e:
                prog.remove_task(task)
                console.print(f"  [red]✗ {pkg} — {e}[/red]")


def _print_next_steps():
    console.print("\n[bold]Prochaines étapes :[/bold]")
    console.print("  [cyan]datasphere wizard[/cyan]          — configurer votre stack")
    console.print("  [cyan]datasphere run <file.json>[/cyan] — générer une architecture")
    console.print("  [cyan]datasphere api --port 8000[/cyan] — lancer l'API REST")
    console.print("  [cyan]datasphere status[/cyan]          — vérifier les services")
