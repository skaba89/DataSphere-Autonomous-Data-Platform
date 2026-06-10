"""
datasphere run — exécute l'orchestrateur multi-agents depuis un fichier JSON ou stdin.

Usage:
  datasphere run request.json --output ./artifacts
  echo '{"business_request":"...","architecture_constraints":{...}}' | datasphere run -
"""
from __future__ import annotations
import json
import sys
import click
from rich.console import Console
from datasphere.agents.orchestrator import AgentOrchestrator, from_json

console = Console()


@click.command()
@click.argument("request_file", default="-")
@click.option("--output", "-o", default="./datasphere-artifacts", help="Dossier de sortie des artifacts")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Sortie minimale")
@click.option("--json-out", is_flag=True, default=False, help="Afficher le résumé en JSON")
def run_agents(request_file: str, output: str, quiet: bool, json_out: bool):
    """
    Lance l'orchestrateur multi-agents sur une demande métier.

    REQUEST_FILE : chemin vers un fichier JSON ou '-' pour lire stdin.

    Format JSON attendu :

    \b
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
    # Read input
    if request_file == "-":
        raw = sys.stdin.read()
    else:
        import pathlib
        raw = pathlib.Path(request_file).read_text()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON invalide : {e}[/red]")
        sys.exit(1)

    from datasphere.models.request import BusinessRequest
    try:
        request = BusinessRequest(**data)
    except Exception as e:
        console.print(f"[red]Erreur de validation de la requête : {e}[/red]")
        sys.exit(1)

    orchestrator = AgentOrchestrator()
    result = orchestrator.run(request, output_dir=output, verbose=not quiet)

    if json_out:
        summary = {
            "success": result.success,
            "request": result.request_summary,
            "artifacts_path": result.artifacts_path,
            "errors": result.errors,
        }
        if result.cost_optimization:
            summary["cost"] = {
                "monthly_usd": result.cost_optimization.total_monthly_usd,
                "yearly_usd": result.cost_optimization.total_yearly_usd,
                "savings_usd": result.cost_optimization.savings_usd,
            }
        console.print_json(json.dumps(summary))

    sys.exit(0 if result.success else 1)
