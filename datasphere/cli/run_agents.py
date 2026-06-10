"""
datasphere run   — flow conversationnel interactif en 5 étapes
datasphere run <file.json>  — génération directe depuis un fichier JSON
datasphere run -  — lit le JSON depuis stdin
"""
from __future__ import annotations
import json
import sys
import pathlib
import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("request_file", default="", required=False)
@click.option("--output", "-o", default="./datasphere-artifacts",
              help="Dossier de sortie des artifacts générés")
@click.option("--quiet", "-q", is_flag=True, default=False,
              help="Sortie minimale")
@click.option("--json-out", is_flag=True, default=False,
              help="Afficher le résumé final en JSON")
def run_agents(request_file: str, output: str, quiet: bool, json_out: bool):
    """
    Lance l'orchestrateur multi-agents.

    \b
    Sans argument      → flow interactif en 5 étapes (recommandé)
    Avec fichier JSON  → génération directe depuis les contraintes fournies
    Avec '-'           → lit le JSON depuis stdin

    \b
    Flow interactif :
      1. Vous exprimez votre besoin métier
      2. L'Orchestrator pose les questions techniques
      3. Le Stack Advisor propose 2-3 architectures
      4. Vous validez une architecture
      5. Les agents génèrent tous les artifacts

    \b
    Format JSON (mode direct) :
    {
      "business_request": "Analyse les ventes par agence",
      "architecture_constraints": {
        "cloud_provider": "aws",
        "data_warehouse": "snowflake",
        "orchestrator": "airflow",
        "ingestion": "airbyte",
        "transformation": "dbt Core",
        "data_lake": "S3",
        "bi_tool": "superset",
        "catalog": "openmetadata",
        "quality": "great-expectations",
        "deployment": "kubernetes",
        "iac": "terraform",
        "security": ["RBAC", "Vault", "RLS"]
      }
    }
    """
    from datasphere.agents.orchestrator import AgentOrchestrator, from_json

    orchestrator = AgentOrchestrator()

    # ── Interactive mode ─────────────────────────────────────────────────────
    if not request_file:
        result = orchestrator.run_interactive(output_dir=output)
        if json_out:
            _print_json_summary(result)
        sys.exit(0 if result.success else 1)

    # ── JSON file or stdin ───────────────────────────────────────────────────
    if request_file == "-":
        raw = sys.stdin.read()
    else:
        p = pathlib.Path(request_file)
        if not p.exists():
            console.print(f"[red]Fichier introuvable : {request_file}[/red]")
            sys.exit(1)
        raw = p.read_text()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON invalide : {e}[/red]")
        sys.exit(1)

    from datasphere.models.request import BusinessRequest
    try:
        request = BusinessRequest(**data)
    except Exception as e:
        console.print(f"[red]Erreur de validation : {e}[/red]")
        sys.exit(1)

    result = orchestrator.run(request, output_dir=output, verbose=not quiet)

    if json_out:
        _print_json_summary(result)

    sys.exit(0 if result.success else 1)


def _print_json_summary(result) -> None:
    summary = {
        "success": result.success,
        "request": result.request_summary,
        "artifacts_path": result.artifacts_path,
        "errors": result.errors,
    }
    if result.cost_optimization:
        summary["cost"] = {
            "monthly_usd":  result.cost_optimization.total_monthly_usd,
            "yearly_usd":   result.cost_optimization.total_yearly_usd,
            "savings_usd":  result.cost_optimization.savings_usd,
        }
    console.print_json(json.dumps(summary))
