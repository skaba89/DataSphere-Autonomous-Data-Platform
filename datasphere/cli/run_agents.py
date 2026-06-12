"""
datasphere run              → sélection interactive Mode 1 ou Mode 2
datasphere run --mode=1     → Mode 1 interactif (stack explicite)
datasphere run --mode=2     → Mode 2 interactif (recommandation)
datasphere run explicit.json  → Mode 1 depuis fichier JSON
datasphere run context.json   → Mode 2 depuis fichier JSON
datasphere run -              → lit le JSON depuis stdin (détection auto du mode)
"""
from __future__ import annotations
import json
import sys
import pathlib
import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("input_file", default="", required=False)
@click.option("--mode", type=click.Choice(["1", "2"]), default=None,
              help="1 = stack explicite | 2 = recommandation agents")
@click.option("--output", "-o", default="./datasphere-artifacts",
              help="Dossier de sortie des artifacts générés")
@click.option("--quiet", "-q", is_flag=True, default=False,
              help="Sortie minimale (pas d'interactivité)")
@click.option("--json-out", is_flag=True, default=False,
              help="Afficher le résumé final en JSON")
def run_agents(input_file: str, mode: str | None, output: str, quiet: bool, json_out: bool):
    """
    Lance la plateforme DataSphere en Mode 1 ou Mode 2.

    \b
    ┌─────────────────────────────────────────────────────┐
    │  MODE 1 — Stack Explicite                           │
    │  Vous choisissez : AWS + Snowflake + Airflow + dbt  │
    │  Les agents valident et génèrent l'infrastructure   │
    │                                                     │
    │  MODE 2 — Recommandation par les agents             │
    │  Vous donnez : budget · volume · sécurité · équipe  │
    │  Les agents proposent 3 architectures → vous validez│
    └─────────────────────────────────────────────────────┘

    \b
    Usages :
      datasphere run                  → choix interactif du mode
      datasphere run --mode=1         → Mode 1 interactif
      datasphere run --mode=2         → Mode 2 interactif
      datasphere run explicit.json    → Mode 1 depuis fichier
      datasphere run context.json     → Mode 2 depuis fichier
      cat request.json | datasphere run -   → depuis stdin

    \b
    Format Mode 1 (stack explicite) :
    {
      "mode": "explicit",
      "business_request": "Analyse les ventes par agence",
      "cloud_provider": "aws",
      "data_warehouse": "snowflake",
      "orchestrator": "airflow",
      "ingestion": "airbyte",
      "transformation": "dbt",
      "bi_tool": "superset",
      "deployment": "kubernetes",
      "security": ["RBAC", "Vault", "RLS"],
      "budget": "enterprise"
    }

    \b
    Format Mode 2 (recommandation) :
    {
      "mode": "recommended",
      "business_request": "Analyse les données hospitalières",
      "budget": "low",
      "data_volume": "medium",
      "security_level": "rbac",
      "team_size": "small",
      "processing_mode": "batch",
      "cloud_preference": "local-docker",
      "must_be_open_source": true
    }
    """
    from datasphere.agents.mode_router import run_interactive, run_explicit, run_recommended
    from datasphere.models.modes import ExplicitStack, RecommendationContext

    # ── No file: interactive ─────────────────────────────────────────────────
    if not input_file:
        if mode == "1":
            from datasphere.agents.mode_router import _interactive_mode1
            stack = _interactive_mode1()
            result = run_explicit(stack, output_dir=output)
        elif mode == "2":
            from datasphere.agents.mode_router import _interactive_mode2
            ctx = _interactive_mode2()
            result = run_recommended(ctx, output_dir=output)
        else:
            result = run_interactive(output_dir=output)

        if json_out:
            _print_json_summary(result)
        sys.exit(0 if result.success else 1)

    # ── File or stdin ────────────────────────────────────────────────────────
    if input_file == "-":
        raw_text = sys.stdin.read()
    else:
        p = pathlib.Path(input_file)
        if not p.exists():
            console.print(f"[red]Fichier introuvable : {input_file}[/red]")
            sys.exit(1)
        raw_text = p.read_text()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON invalide : {e}[/red]")
        sys.exit(1)

    detected_mode = data.get("mode", "explicit")

    if detected_mode == "recommended":
        try:
            ctx = RecommendationContext(**{k: v for k, v in data.items() if k != "mode"})
        except Exception as e:
            console.print(f"[red]Erreur validation Mode 2 : {e}[/red]")
            sys.exit(1)
        result = run_recommended(ctx, output_dir=output, verbose=not quiet)

    else:
        # Mode 1 — support both new format and legacy BusinessRequest format
        if "architecture_constraints" in data:
            # Legacy format → convert
            data = _legacy_to_explicit(data)
        try:
            stack = ExplicitStack(**{k: v for k, v in data.items() if k != "mode"})
        except Exception as e:
            console.print(f"[red]Erreur validation Mode 1 : {e}[/red]")
            sys.exit(1)
        result = run_explicit(stack, output_dir=output, verbose=not quiet)

    if json_out:
        _print_json_summary(result)
    sys.exit(0 if result.success else 1)


def _legacy_to_explicit(data: dict) -> dict:
    """Convert old BusinessRequest format to ExplicitStack format."""
    c = data.get("architecture_constraints", {})
    return {
        "mode": "explicit",
        "business_request": data.get("business_request", ""),
        "cloud_provider":   c.get("cloud_provider", "local-docker"),
        "data_warehouse":   c.get("data_warehouse", "postgresql"),
        "orchestrator":     c.get("orchestrator", "airflow"),
        "ingestion":        c.get("ingestion", "airbyte"),
        "transformation":   c.get("transformation", "dbt"),
        "data_lake":        c.get("data_lake"),
        "bi_tool":          c.get("bi_tool", "superset"),
        "catalog":          c.get("catalog"),
        "quality":          c.get("quality"),
        "deployment":       c.get("deployment", "docker-compose"),
        "iac":              c.get("iac"),
        "security":         c.get("security", []),
        "budget":           c.get("budget", "medium"),
        "data_volume":      c.get("data_volume", "medium"),
        "processing_mode":  c.get("processing_mode", "batch"),
        "region":           c.get("region"),
    }


def _print_json_summary(result) -> None:
    summary = {
        "success":        result.success,
        "request":        result.request_summary,
        "artifacts_path": result.artifacts_path,
        "errors":         result.errors,
    }
    if result.cost_optimization:
        summary["cost"] = {
            "monthly_usd": result.cost_optimization.total_monthly_usd,
            "yearly_usd":  result.cost_optimization.total_yearly_usd,
            "savings_usd": result.cost_optimization.savings_usd,
        }
    console.print_json(json.dumps(summary))
