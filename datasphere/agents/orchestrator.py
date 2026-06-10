"""
Agent Orchestrator — coordinates all specialized agents in sequence.

Flow:
  BusinessRequest
    → StackAdvisorAgent      (validate compatibility)
    → CloudArchitectAgent    (cloud topology)
    → InfrastructureAgent    (generate infra files)
    → CostOptimizationAgent  (estimate + optimize costs)
    → SecurityComplianceAgent (RBAC, RLS, secrets)
    → DeploymentAgent        (CI/CD, monitoring)
    → OrchestratorOutput     (all artifacts consolidated)
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from datasphere.agents.base_agent import BaseAgent
from datasphere.agents.stack_advisor import StackAdvisorAgent
from datasphere.agents.cloud_architect import CloudArchitectAgent
from datasphere.agents.infrastructure import InfrastructureAgent
from datasphere.agents.cost_optimization import CostOptimizationAgent
from datasphere.agents.security_compliance import SecurityComplianceAgent
from datasphere.agents.deployment import DeploymentAgent
from datasphere.models.request import BusinessRequest
from datasphere.models.output import AgentOutput, OrchestratorOutput

console = Console()

AGENT_PIPELINE: list[tuple[str, type[BaseAgent]]] = [
    ("stack_advisor",       StackAdvisorAgent),
    ("cloud_architect",     CloudArchitectAgent),
    ("infrastructure",      InfrastructureAgent),
    ("cost_optimization",   CostOptimizationAgent),
    ("security_compliance", SecurityComplianceAgent),
    ("deployment",          DeploymentAgent),
]

AGENT_LABELS = {
    "stack_advisor":       "Stack Advisor        — validation compatibilité",
    "cloud_architect":     "Cloud Architect      — topologie cloud",
    "infrastructure":      "Infrastructure       — génération fichiers infra",
    "cost_optimization":   "Cost Optimization    — estimation et optimisations",
    "security_compliance": "Security & Compliance — RBAC, RLS, secrets",
    "deployment":          "Deployment           — CI/CD et monitoring",
}


class AgentOrchestrator:
    """
    Runs all agents in sequence, passing accumulated context.
    Each agent sees the outputs of all previous agents.
    """

    def run(
        self,
        request: BusinessRequest,
        output_dir: str | None = None,
        verbose: bool = True,
    ) -> OrchestratorOutput:
        request = request.normalized()
        result = OrchestratorOutput(request_summary=request.business_request)
        context: dict[str, AgentOutput] = {}

        if verbose:
            console.print(Panel.fit(
                f"[bold green]DataSphere Agent Orchestrator[/bold green]\n"
                f"[dim]{request.business_request}[/dim]\n"
                f"[cyan]{request.architecture_constraints.cloud_provider}[/cyan] | "
                f"[cyan]{request.architecture_constraints.data_warehouse}[/cyan] | "
                f"[cyan]{request.architecture_constraints.orchestrator}[/cyan] | "
                f"[cyan]{request.architecture_constraints.bi_tool}[/cyan]",
                border_style="green",
                padding=(1, 2),
            ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            for key, agent_cls in AGENT_PIPELINE:
                label = AGENT_LABELS[key]
                task = progress.add_task(f"[cyan]{label}...", total=None)
                agent = agent_cls()
                output = agent.run(request, context)
                context[key] = output
                setattr(result, key, output)
                if not output.success:
                    result.errors.extend(output.errors)
                progress.remove_task(task)

        result.success = len(result.errors) == 0

        if output_dir:
            result.artifacts_path = self._write_artifacts(result, output_dir)

        if verbose:
            self._print_summary(result)

        return result

    def _write_artifacts(self, result: OrchestratorOutput, output_dir: str) -> str:
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

        # Write consolidated index
        index = self._build_index(result)
        (base / "README.md").write_text(index, encoding="utf-8")

        return str(base)

    def _build_index(self, result: OrchestratorOutput) -> str:
        lines = [
            f"# DataSphere — Artifacts",
            f"",
            f"**Request:** {result.request_summary}",
            f"",
            "## Generated Files",
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

        if result.cost_optimization:
            co = result.cost_optimization
            lines += [
                "## Cost Summary",
                "",
                f"- **Monthly estimate:** ${co.total_monthly_usd:,.2f}",
                f"- **Annual estimate:** ${co.total_yearly_usd:,.2f}",
                f"- **Potential savings:** ${co.savings_usd:,.2f}/month",
                "",
            ]
        return "\n".join(lines)

    def _print_summary(self, result: OrchestratorOutput) -> None:
        console.print()

        # Stack table
        if result.stack_advisor and result.stack_advisor.validated_stack:
            table = Table(
                title="Stack validée",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("Couche", style="cyan", min_width=16)
            table.add_column("Outil", style="bold magenta", min_width=20)
            for layer, tool in result.stack_advisor.validated_stack.items():
                table.add_row(layer, tool)
            console.print(table)

        # Warnings
        if result.stack_advisor and result.stack_advisor.warnings:
            console.print("\n[bold yellow]⚠️  Avertissements Stack Advisor[/bold yellow]")
            for w in result.stack_advisor.warnings:
                console.print(f"  [yellow]•[/yellow] {w}")

        # Cloud recommendations
        if result.cloud_architect and result.cloud_architect.recommendations:
            console.print("\n[bold blue]☁️  Recommandations Cloud Architect[/bold blue]")
            for r in result.cloud_architect.recommendations:
                console.print(f"  [blue]•[/blue] {r}")

        # Cost summary
        if result.cost_optimization:
            co = result.cost_optimization
            console.print(
                f"\n[bold green]💶  Coût estimé : "
                f"${co.total_monthly_usd:,.0f}/mois  |  "
                f"${co.total_yearly_usd:,.0f}/an[/bold green]"
            )
            if co.savings_usd > 0:
                console.print(
                    f"[green]   Économie potentielle : ${co.savings_usd:,.0f}/mois "
                    f"en passant à l'open-source[/green]"
                )

        # Artifacts
        if result.artifacts_path:
            console.print(f"\n[bold]📁  Artifacts générés dans :[/bold] {result.artifacts_path}")

        # Status
        if result.success:
            console.print("\n[bold green]✓ Orchestration terminée avec succès.[/bold green]")
        else:
            console.print("\n[bold red]✗ Orchestration terminée avec erreurs :[/bold red]")
            for e in result.errors:
                console.print(f"  [red]•[/red] {e}")


def from_json(data: dict[str, Any]) -> BusinessRequest:
    """Parse raw dict (from JSON input) into BusinessRequest."""
    return BusinessRequest(**data)


def from_json_file(path: str) -> BusinessRequest:
    return from_json(json.loads(Path(path).read_text()))


def from_json_string(s: str) -> BusinessRequest:
    return from_json(json.loads(s))
