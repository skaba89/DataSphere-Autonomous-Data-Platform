"""
Agent Orchestrator — implémente le flow conversationnel en 5 étapes.

Étape 1 : L'humain exprime son besoin métier
Étape 2 : L'Orchestrator demande les contraintes techniques (DialogueAgent)
Étape 3 : Le Stack Advisor propose 2 ou 3 architectures (ArchitectureProposer)
Étape 4 : L'humain valide une architecture
Étape 5 : Les 6 agents génèrent tout selon la stack validée
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.columns import Columns
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from datasphere.agents.base_agent import BaseAgent
from datasphere.agents.stack_advisor import StackAdvisorAgent
from datasphere.agents.cloud_architect import CloudArchitectAgent
from datasphere.agents.infrastructure import InfrastructureAgent
from datasphere.agents.cost_optimization import CostOptimizationAgent
from datasphere.agents.security_compliance import SecurityComplianceAgent
from datasphere.agents.deployment import DeploymentAgent
from datasphere.models.request import BusinessRequest, ArchitectureConstraints
from datasphere.models.output import AgentOutput, OrchestratorOutput
from datasphere.models.conversation import ArchitectureProposal, ConversationState
from datasphere.generators.dbt_project import DbtProjectGenerator
from datasphere.generators.airflow_dag import AirflowDagGenerator

console = Console()

GENERATION_PIPELINE: list[tuple[str, type[BaseAgent]]] = [
    ("stack_advisor",       StackAdvisorAgent),
    ("cloud_architect",     CloudArchitectAgent),
    ("infrastructure",      InfrastructureAgent),
    ("cost_optimization",   CostOptimizationAgent),
    ("security_compliance", SecurityComplianceAgent),
    ("deployment",          DeploymentAgent),
]

AGENT_LABELS = {
    "stack_advisor":       "Stack Advisor        — validation finale",
    "cloud_architect":     "Cloud Architect      — topologie cloud",
    "infrastructure":      "Infrastructure       — génération fichiers",
    "cost_optimization":   "Cost Optimization    — estimation coûts",
    "security_compliance": "Security & Compliance — RBAC, RLS, secrets",
    "deployment":          "Deployment           — CI/CD et monitoring",
}


# ---------------------------------------------------------------------------
# Step 1 — Collect business request
# ---------------------------------------------------------------------------

def _step1_business_request() -> str:
    console.print(Panel.fit(
        "[bold green]DataSphere — Agent Orchestrator[/bold green]\n"
        "[dim]Plateforme de données autonome et stack-agnostic[/dim]",
        border_style="green",
        padding=(1, 4),
    ))
    console.print(f"\n{Rule('[bold cyan]Étape 1 — Besoin métier[/bold cyan]')}")
    console.print("[dim]Décrivez en une phrase ce que vous voulez analyser ou construire.[/dim]")
    console.print("[dim]Exemples : \"Analyse les ventes par agence\", \"Suivi des données hospitalières\"[/dim]\n")

    while True:
        request = console.input("[bold]Votre besoin métier :[/bold] ").strip()
        if len(request) > 5:
            return request
        console.print("[red]Veuillez décrire votre besoin (au moins 6 caractères).[/red]")


# ---------------------------------------------------------------------------
# Step 3 — Display proposals
# ---------------------------------------------------------------------------

COMPLEXITY_COLOR = {"low": "green", "medium": "yellow", "high": "red"}


def _step3_display_proposals(proposals: list[ArchitectureProposal]) -> None:
    console.print(f"\n{Rule('[bold cyan]Étape 3 — Architectures proposées[/bold cyan]')}")
    console.print("[dim]Le Stack Advisor a généré les architectures suivantes pour votre contexte.[/dim]\n")

    for p in proposals:
        color = COMPLEXITY_COLOR.get(p.complexity, "white")

        # Header
        console.print(Panel(
            f"[bold]{p.name}[/bold]\n[dim]{p.tagline}[/dim]",
            title=f"[bold cyan]Option {p.id}[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        ))

        # Stack table
        stack = p.constraints
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column("Couche", style="dim", min_width=18)
        t.add_column("Outil", style="bold magenta")
        t.add_row("Cloud",          stack.cloud_provider)
        t.add_row("Warehouse",      stack.data_warehouse)
        t.add_row("Orchestration",  stack.orchestrator)
        t.add_row("Ingestion",      stack.ingestion)
        t.add_row("Transformation", stack.transformation)
        t.add_row("Storage",        stack.data_lake or "—")
        t.add_row("BI",             stack.bi_tool)
        t.add_row("Qualité",        stack.quality or "—")
        t.add_row("Catalog",        stack.catalog or "—")
        t.add_row("Déploiement",    stack.deployment)
        console.print(t)

        # Pros / Cons
        pros_text = "\n".join(f"  [green]+[/green] {p}" for p in p.pros)
        cons_text = "\n".join(f"  [red]−[/red] {c}" for c in p.cons if c)

        console.print(pros_text)
        if cons_text:
            console.print(cons_text)

        console.print(
            f"\n  [bold]Coût estimé :[/bold] [yellow]~${p.estimated_monthly_usd:,.0f}/mois[/yellow]  "
            f"|  [bold]Complexité :[/bold] [{color}]{p.complexity}[/{color}]  "
            f"|  [bold]Délai :[/bold] {p.time_to_deploy}"
        )
        console.print(f"  [dim]Idéal pour : {p.best_for}[/dim]\n")


# ---------------------------------------------------------------------------
# Step 4 — Human choice
# ---------------------------------------------------------------------------

def _step4_choose_proposal(proposals: list[ArchitectureProposal]) -> ArchitectureProposal:
    console.print(f"{Rule('[bold cyan]Étape 4 — Votre choix[/bold cyan]')}")

    for p in proposals:
        console.print(
            f"  [cyan]{p.id}.[/cyan]  [bold]{p.name}[/bold] "
            f"[dim]— ~${p.estimated_monthly_usd:,.0f}/mois, complexité {p.complexity}[/dim]"
        )

    console.print()

    while True:
        raw = console.input(
            f"  Choisissez une architecture [1-{len(proposals)}] "
            "(ou tapez [bold]c[/bold] pour personnaliser) : "
        ).strip().lower()

        if raw == "c":
            return _customise_proposal(proposals)

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(proposals):
                chosen = proposals[idx]
                console.print(
                    f"\n[bold green]✓ Architecture choisie : Option {chosen.id} — {chosen.name}[/bold green]"
                )
                return chosen
        except ValueError:
            pass
        console.print(f"  [red]Choix invalide — entrez un nombre entre 1 et {len(proposals)} ou 'c'.[/red]")


def _customise_proposal(proposals: list[ArchitectureProposal]) -> ArchitectureProposal:
    """Let the human pick a base proposal then adjust individual tools."""
    from datasphere.core.config import ALLOWED

    console.print("\n[bold yellow]Personnalisation[/bold yellow]")
    console.print("Choisissez d'abord la proposition de base à modifier :")

    for p in proposals:
        console.print(f"  [cyan]{p.id}.[/cyan]  {p.name}")

    while True:
        raw = console.input(f"  Base [1-{len(proposals)}] : ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(proposals):
                base = proposals[idx]
                break
        except ValueError:
            pass

    # Ask which layers to change
    console.print("\n[dim]Appuyez sur Entrée pour conserver le choix de la proposition de base.[/dim]")
    overrides: dict[str, str] = {}

    adjustable = {
        "warehouse":      "data_warehouse",
        "orchestrator":   "orchestrator",
        "ingestion":      "ingestion",
        "transformation": "transformation",
        "bi":             "bi_tool",
        "quality":        "quality",
        "catalog":        "catalog",
    }

    for ui_name, field in adjustable.items():
        current = getattr(base.constraints, field, "") or ""
        options = ALLOWED.get(ui_name if ui_name != "orchestrator" else "orchestration", [])
        console.print(f"\n  [cyan]{ui_name}[/cyan] actuel : [magenta]{current}[/magenta]")
        for i, opt in enumerate(options, 1):
            marker = " [green]←[/green]" if opt == current else ""
            console.print(f"    {i}. {opt}{marker}")
        raw = console.input(f"  Nouveau choix [1-{len(options)}] (Entrée = conserver) : ").strip()
        if raw:
            try:
                cidx = int(raw) - 1
                if 0 <= cidx < len(options):
                    overrides[field] = options[cidx]
            except ValueError:
                pass

    # Build customised proposal
    constraint_data = base.constraints.model_dump()
    constraint_data.update(overrides)
    custom_constraints = ArchitectureConstraints(**constraint_data)

    return ArchitectureProposal(
        id=0,
        name=f"{base.name} (personnalisée)",
        tagline="Architecture personnalisée par l'humain",
        constraints=custom_constraints,
        pros=base.pros + ["Adaptée à vos contraintes spécifiques"],
        cons=base.cons,
        estimated_monthly_usd=base.estimated_monthly_usd,
        complexity=base.complexity,
        time_to_deploy=base.time_to_deploy,
        best_for="Votre contexte spécifique",
    )


# ---------------------------------------------------------------------------
# Step 5 — Generation
# ---------------------------------------------------------------------------

def _step5_generate(
    business_request: str,
    proposal: ArchitectureProposal,
    output_dir: str | None,
) -> OrchestratorOutput:
    console.print(f"\n{Rule('[bold cyan]Étape 5 — Génération[/bold cyan]')}")
    console.print(
        f"[dim]Architecture : [bold]{proposal.name}[/bold]  "
        f"|  {proposal.constraints.cloud_provider} / "
        f"{proposal.constraints.data_warehouse} / "
        f"{proposal.constraints.orchestrator}[/dim]\n"
    )

    request = BusinessRequest(
        business_request=business_request,
        architecture_constraints=proposal.constraints,
    ).normalized()

    result = OrchestratorOutput(request_summary=business_request)
    context: dict[str, AgentOutput] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        for key, agent_cls in GENERATION_PIPELINE:
            label = AGENT_LABELS[key]
            task = progress.add_task(f"[cyan]{label}...", total=None)
            output = agent_cls().run(request, context)
            context[key] = output
            setattr(result, key, output)
            if not output.success:
                result.errors.extend(output.errors)
            progress.remove_task(task)

    result.success = len(result.errors) == 0

    if output_dir:
        result.artifacts_path = _write_artifacts(result, output_dir, proposal)

    _print_generation_summary(result, proposal)
    return result


def _write_artifacts(
    result: OrchestratorOutput, output_dir: str, proposal: ArchitectureProposal
) -> str:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    for attr in ("stack_advisor", "cloud_architect", "infrastructure",
                 "cost_optimization", "security_compliance", "deployment"):
        agent_output: AgentOutput | None = getattr(result, attr, None)
        if agent_output and agent_output.artifacts:
            for filename, content in agent_output.artifacts.items():
                filepath = base / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")

    import logging as _logging
    _log = _logging.getLogger(__name__)

    # Generate dbt project scaffold
    try:
        dbt_files = DbtProjectGenerator().generate(
            result.request_summary, proposal.constraints
        )
        for rel_path, content in dbt_files.files.items():
            filepath = base / "dbt" / rel_path
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
    except Exception as exc:
        _log.warning("dbt_scaffold_failed", extra={"error": str(exc)})

    # Generate Airflow DAGs if orchestrator is Airflow
    if proposal.constraints.orchestrator.lower() in ("airflow", "apache airflow"):
        try:
            dag_files = AirflowDagGenerator().generate(
                result.request_summary, proposal.constraints
            )
            for rel_path, content in dag_files.files.items():
                filepath = base / "dags" / rel_path
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")
        except Exception as exc:
            _log.warning("airflow_dag_failed", extra={"error": str(exc)})

    (base / "README.md").write_text(_build_index(result, proposal), encoding="utf-8")
    return str(base)


def _build_index(result: OrchestratorOutput, proposal: ArchitectureProposal) -> str:
    c = proposal.constraints
    lines = [
        f"# DataSphere Artifacts — {result.request_summary}",
        "",
        f"**Architecture choisie :** {proposal.name}",
        f"**Stack :** {c.cloud_provider} | {c.data_warehouse} | {c.orchestrator} | {c.bi_tool}",
        "",
        "## Fichiers générés",
        "",
    ]
    for attr in ("stack_advisor", "cloud_architect", "infrastructure",
                 "cost_optimization", "security_compliance", "deployment"):
        agent_output = getattr(result, attr, None)
        if agent_output and agent_output.artifacts:
            lines.append(f"### {attr.replace('_', ' ').title()}")
            for filename in agent_output.artifacts:
                lines.append(f"- [{filename}]({filename})")
            lines.append("")

    lines += [
        "### dbt Project",
        "- [dbt/dbt_project.yml](dbt/dbt_project.yml)",
        "- [dbt/profiles.yml](dbt/profiles.yml)",
        "- [dbt/models/staging/](dbt/models/staging/)",
        "- [dbt/models/marts/](dbt/models/marts/)",
        "",
    ]

    if c.orchestrator.lower() in ("airflow", "apache airflow"):
        lines += [
            "### Airflow DAGs",
            "- [dags/](dags/)",
            "",
        ]

    if result.cost_optimization:
        co = result.cost_optimization
        lines += [
            "## Résumé des coûts",
            "",
            f"- **Mensuel :** ${co.total_monthly_usd:,.2f}",
            f"- **Annuel :** ${co.total_yearly_usd:,.2f}",
            f"- **Économie potentielle :** ${co.savings_usd:,.2f}/mois",
            "",
        ]
    return "\n".join(lines)


def _print_generation_summary(result: OrchestratorOutput, proposal: ArchitectureProposal) -> None:
    console.print()

    if result.stack_advisor and result.stack_advisor.warnings:
        console.print("[bold yellow]⚠️  Avertissements[/bold yellow]")
        for w in result.stack_advisor.warnings:
            console.print(f"  [yellow]•[/yellow] {w}")
        console.print()

    if result.cloud_architect and result.cloud_architect.recommendations:
        recs = [r for r in result.cloud_architect.recommendations if "aucun conflit" not in r]
        if recs:
            console.print("[bold blue]☁️  Recommandations cloud[/bold blue]")
            for r in recs:
                console.print(f"  [blue]•[/blue] {r}")
            console.print()

    if result.cost_optimization:
        co = result.cost_optimization
        console.print(
            f"[bold green]💶  Coût estimé : "
            f"${co.total_monthly_usd:,.0f}/mois  |  "
            f"${co.total_yearly_usd:,.0f}/an[/bold green]"
        )
        if co.savings_usd > 0:
            console.print(
                f"[green]   Économie potentielle (stack open-source) : "
                f"${co.savings_usd:,.0f}/mois[/green]"
            )
        console.print()

    if result.artifacts_path:
        console.print(f"[bold]📁  Artifacts générés dans :[/bold] {result.artifacts_path}\n")

    if result.success:
        console.print("[bold green]✓ Génération terminée avec succès.[/bold green]")
    else:
        console.print("[bold red]✗ Génération terminée avec erreurs :[/bold red]")
        for e in result.errors:
            console.print(f"  [red]•[/red] {e}")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """
    Implémente le flow conversationnel en 5 étapes.
    Peut être utilisé en mode interactif (CLI) ou programmatique (JSON input).
    """

    def run_interactive(self, output_dir: str | None = "./datasphere-artifacts") -> OrchestratorOutput:
        """Mode interactif — flow complet en 5 étapes."""
        from datasphere.agents.dialogue import collect_constraints
        from datasphere.agents.proposer import generate_proposals

        # Étape 1
        business_request = _step1_business_request()

        # Étape 2
        raw_constraints = collect_constraints(business_request)

        # Étape 3
        proposals = generate_proposals(raw_constraints)
        _step3_display_proposals(proposals)

        # Étape 4
        chosen = _step4_choose_proposal(proposals)

        # Étape 5
        return _step5_generate(business_request, chosen, output_dir)

    def run(
        self,
        request: BusinessRequest,
        output_dir: str | None = None,
        verbose: bool = True,
    ) -> OrchestratorOutput:
        """Mode programmatique — utilisé par les tests et l'API JSON."""
        from datasphere.agents.proposer import generate_proposals

        request = request.normalized()
        c = request.architecture_constraints

        # If constraints are fully specified, skip proposal step
        if c.data_warehouse != "auto":
            proposal = ArchitectureProposal(
                id=1,
                name="Stack fournie",
                tagline="Architecture fournie directement sans proposition",
                constraints=c,
                pros=[],
                cons=[],
                estimated_monthly_usd=0.0,
                complexity="medium",
                time_to_deploy="",
                best_for="",
            )
            return _step5_generate(request.business_request, proposal, output_dir)

        # Otherwise generate proposals and pick the first (non-interactive)
        raw = c.model_dump()
        proposals = generate_proposals(raw)
        if verbose:
            _step3_display_proposals(proposals)
        return _step5_generate(request.business_request, proposals[0], output_dir)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def from_json(data: dict[str, Any]) -> BusinessRequest:
    return BusinessRequest(**data)


def from_json_file(path: str) -> BusinessRequest:
    return from_json(json.loads(Path(path).read_text()))


def from_json_string(s: str) -> BusinessRequest:
    return from_json(json.loads(s))
