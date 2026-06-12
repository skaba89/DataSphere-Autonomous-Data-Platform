"""
DataSphere CLI — interactive command-line interface.

Usage:
    datasphere                    # Interactive REPL
    datasphere generate           # Guided generation wizard
    datasphere serve              # Start API server
    datasphere status             # Check server health
    datasphere templates          # Browse stack templates
    datasphere diff               # Compare two stacks
    datasphere version            # Show version
"""
from __future__ import annotations

import argparse
import cmd
import json
import os
import sys
import textwrap
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VERSION = "1.2.0"

_BANNER = r"""
╔══════════════════════════════════════╗
║  DataSphere Autonomous Data Platform ║
║  Type 'help' for commands            ║
╚══════════════════════════════════════╝"""

# Prompt input helper — allows tests to inject via monkeypatch
def _input(prompt: str = "") -> str:  # pragma: no cover
    return input(prompt)


def _print(msg: str = "") -> None:
    print(msg)


# ---------------------------------------------------------------------------
# Templates helpers
# ---------------------------------------------------------------------------

def _get_templates():
    from datasphere.generators.templates import TemplateRegistry
    return TemplateRegistry()


def _fmt_templates_table(templates) -> str:
    lines = []
    header = f"{'ID':<30} {'Name':<30} {'Cost/mo':<10} {'Complexity'}"
    lines.append(header)
    lines.append("-" * len(header))
    for t in templates:
        cost = f"${t.estimated_monthly_usd:,}" if t.estimated_monthly_usd else "Free"
        lines.append(f"{t.id:<30} {t.name:<30} {cost:<10} {t.complexity}")
    return "\n".join(lines)


def _fmt_template_detail(t) -> str:
    c = t.constraints
    stack_parts = [
        c.get("warehouse", ""),
        c.get("orchestrator", ""),
        c.get("transformation", ""),
        c.get("bi_tool", ""),
    ]
    stack_str = " + ".join(p for p in stack_parts if p)
    cost = f"${t.estimated_monthly_usd:,}/month" if t.estimated_monthly_usd else "Free"
    use_cases = ", ".join(t.use_cases) if t.use_cases else "General analytics"
    lines = [
        f"Name:       {t.name}",
        f"Category:   {t.category}",
        f"Stack:      {stack_str}",
        f"Cost:       {cost}",
        f"Complexity: {t.complexity}",
        f"Deploy:     {t.time_to_deploy}",
        f"Use cases:  {use_cases}",
    ]
    if t.pros:
        lines.append(f"Pros:       {', '.join(t.pros)}")
    if t.cons:
        lines.append(f"Cons:       {', '.join(t.cons)}")
    if t.tags:
        lines.append(f"Tags:       {', '.join(t.tags)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _fmt_migration_plan(plan) -> str:
    lines = ["Migration plan:"]
    for c in plan.changes:
        if c.change_type == "replace":
            lines.append(f"  {c.from_tool} -> {c.to_tool}: {c.risk.upper()} risk, {c.estimated_days} days")
            for i, step in enumerate(c.migration_steps[:5], 1):
                lines.append(f"    {i}. {step}")
        elif c.change_type == "add":
            lines.append(f"  + {c.to_tool} ({c.component}): {c.estimated_days} days")
        elif c.change_type == "remove":
            lines.append(f"  - {c.from_tool} ({c.component}): {c.estimated_days} days")
    lines.append(f"Total: {plan.total_estimated_days} days estimated")
    lines.append(f"Overall risk: {plan.overall_risk.upper()}")
    lines.append(f"Summary: {plan.summary}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------

class DataSphereCLI(cmd.Cmd):
    intro = _BANNER
    prompt = "datasphere> "

    # ---- generate --------------------------------------------------------

    def do_generate(self, args: str) -> None:
        """Guided generation wizard. Usage: generate [business_request]"""
        request = args.strip()
        if not request:
            request = _input("Business request: ").strip()
        if not request:
            _print("Error: business request is required.")
            return

        cloud = _input("Cloud provider [aws/gcp/azure/other] (aws): ").strip() or "aws"
        warehouse = _input(
            "Data warehouse [snowflake/bigquery/redshift/postgresql/clickhouse/duckdb] (snowflake): "
        ).strip() or "snowflake"
        orchestrator = _input(
            "Orchestrator [airflow/dagster/prefect] (airflow): "
        ).strip() or "airflow"
        budget = _input("Budget [low/medium/enterprise] (medium): ").strip() or "medium"

        _print("[Generating... this may take a moment]")

        # Try server first, fall back to local
        result = _run_generate_local(
            business_request=request,
            cloud=cloud,
            warehouse=warehouse,
            orchestrator=orchestrator,
            budget=budget,
        )

        _print(f"✓ Stack: {result['stack_summary']}")
        _print(f"✓ Estimated cost: ${result['estimated_monthly_usd']:,}/month")
        warnings = result.get("warnings", [])
        if warnings:
            _print(f"✓ {len(warnings)} warning(s)")
            for w in warnings:
                _print(f"  - {w}")

        save = _input("\nSave result? [y/N]: ").strip().lower()
        if save == "y":
            filename = f"datasphere-result-{date.today().strftime('%Y%m%d')}.json"
            with open(filename, "w") as fh:
                json.dump(result, fh, indent=2)
            _print(f"Saved: {filename}")

    def help_generate(self) -> None:
        _print("generate [business_request]")
        _print("  Guided wizard to generate a data architecture.")
        _print("  Prompts for cloud, warehouse, orchestrator, and budget.")

    # ---- templates -------------------------------------------------------

    def do_templates(self, args: str) -> None:
        """Browse stack templates. Usage: templates [template_id]"""
        template_id = args.strip()
        registry = _get_templates()
        if template_id:
            t = registry.get(template_id)
            if t:
                _print(_fmt_template_detail(t))
            else:
                _print(f"Template '{template_id}' not found.")
                _print("Use 'templates' with no argument to list all templates.")
        else:
            templates = registry.list_all()
            _print(_fmt_templates_table(templates))

    def help_templates(self) -> None:
        _print("templates [template_id]")
        _print("  List all available stack templates.")
        _print("  Provide a template ID to see full detail.")

    # ---- diff ------------------------------------------------------------

    def do_diff(self, args: str) -> None:
        """Compare two stacks and show migration plan. Usage: diff"""
        _print("Current stack:")
        from_wh = _input("  Warehouse [snowflake/bigquery/redshift/postgresql/clickhouse/duckdb]: ").strip()
        from_orch = _input("  Orchestrator [airflow/dagster/prefect]: ").strip()

        _print("Target stack:")
        to_wh = _input("  Warehouse: ").strip()
        to_orch = _input("  Orchestrator: ").strip()

        from_stack: dict[str, str] = {}
        to_stack: dict[str, str] = {}

        if from_wh:
            from_stack["data_warehouse"] = from_wh
        if from_orch:
            from_stack["orchestrator"] = from_orch
        if to_wh:
            to_stack["data_warehouse"] = to_wh
        if to_orch:
            to_stack["orchestrator"] = to_orch

        if not from_stack and not to_stack:
            _print("No stack information provided.")
            return

        from datasphere.generators.stack_diff import StackDiffGenerator
        gen = StackDiffGenerator()
        plan = gen.diff(from_stack, to_stack)
        _print("")
        _print(_fmt_migration_plan(plan))

    def help_diff(self) -> None:
        _print("diff")
        _print("  Compare current and target stacks, showing migration plan.")

    # ---- status ----------------------------------------------------------

    def do_status(self, args: str) -> None:
        """Check server health. Usage: status [server_url]"""
        server = args.strip() or "http://localhost:8000"
        _check_status(server)

    def help_status(self) -> None:
        _print("status [server_url]")
        _print("  Check DataSphere API server health.")
        _print("  Default server: http://localhost:8000")

    # ---- serve -----------------------------------------------------------

    def do_serve(self, args: str) -> None:
        """Start the DataSphere API server. Usage: serve [--port PORT]"""
        port = 8000
        parts = args.split()
        for i, p in enumerate(parts):
            if p in ("--port", "-p") and i + 1 < len(parts):
                try:
                    port = int(parts[i + 1])
                except ValueError:
                    pass
        _start_server(host="0.0.0.0", port=port, reload=False, workers=1)

    def help_serve(self) -> None:
        _print("serve [--port PORT]")
        _print("  Start the DataSphere API server (requires uvicorn).")

    # ---- version ---------------------------------------------------------

    def do_version(self, args: str) -> None:
        """Show DataSphere version."""
        _print(f"DataSphere v{_VERSION}")

    # ---- quit / exit -----------------------------------------------------

    def do_quit(self, args: str) -> bool:
        """Exit the DataSphere REPL."""
        _print("Goodbye!")
        return True

    def do_exit(self, args: str) -> bool:
        """Exit the DataSphere REPL."""
        return self.do_quit(args)

    def do_EOF(self, args: str) -> bool:  # pragma: no cover
        _print("")
        return self.do_quit(args)

    # ---- tab completion --------------------------------------------------

    def get_names(self):
        return [n for n in dir(self.__class__) if n.startswith("do_")]

    def completenames(self, text, *ignored):
        commands = [
            "generate", "templates", "diff", "status", "serve", "version",
            "quit", "exit", "help",
        ]
        return [c for c in commands if c.startswith(text)]


# ---------------------------------------------------------------------------
# Shared command implementations (used by REPL and argparse dispatch)
# ---------------------------------------------------------------------------

def _run_generate_local(
    business_request: str,
    cloud: str = "aws",
    warehouse: str = "snowflake",
    orchestrator: str = "airflow",
    budget: str = "medium",
) -> dict[str, Any]:
    """Run generation locally without a server, using generators directly."""
    from datasphere.agents.cost_tables import CostCalculator

    stack = {
        "cloud_provider": cloud,
        "data_warehouse": warehouse,
        "orchestrator": orchestrator,
        "ingestion": "airbyte",
        "transformation": "dbt",
        "bi_tool": "metabase",
        "deployment": "kubernetes",
        "budget": budget,
    }

    calc = CostCalculator()
    breakdown = calc.calculate(stack, budget=budget)

    warnings: list[str] = []
    if warehouse == "duckdb":
        warnings.append("duckdb is recommended for dev workloads, not production.")
    if budget == "low" and warehouse in ("snowflake", "bigquery"):
        warnings.append(f"{warehouse} may exceed low budget expectations.")

    stack_summary = f"{warehouse} + {orchestrator} + dbt + metabase"

    return {
        "business_request": business_request,
        "cloud": cloud,
        "warehouse": warehouse,
        "orchestrator": orchestrator,
        "budget": budget,
        "stack_summary": stack_summary,
        "estimated_monthly_usd": int(breakdown.total_monthly_usd),
        "validated_stack": stack,
        "warnings": warnings,
    }


def _run_generate_with_server(
    server: str,
    business_request: str,
    cloud: str = "aws",
    warehouse: str = "snowflake",
    orchestrator: str = "airflow",
    budget: str = "medium",
) -> dict[str, Any] | None:
    """Try to run generation via the API server. Returns None if unavailable."""
    try:
        from datasphere.client import DataSphereClient
        client = DataSphereClient(server, timeout=60)
        result = client.generate(
            business_request=business_request,
            cloud_provider=cloud,
            data_warehouse=warehouse,
            orchestrator=orchestrator,
            ingestion="airbyte",
            transformation="dbt",
            bi_tool="metabase",
            deployment="kubernetes",
            budget=budget,
        )
        return result
    except Exception:
        return None


def _check_status(server: str) -> None:
    """Print server health status."""
    try:
        try:
            import httpx
            resp = httpx.get(f"{server}/health", timeout=5)
            data = resp.json()
        except ImportError:
            import urllib.request
            import urllib.error
            req = urllib.request.urlopen(f"{server}/health", timeout=5)
            data = json.loads(req.read().decode())

        status = data.get("status", "unknown")
        version = data.get("version", _VERSION)
        _print(f"Server: {server}")
        _print(f"Status: ✓ {status} (v{version})")
        if "job_store" in data:
            _print(f"Job store: ✓ {data['job_store']}")
        if "artifact_store" in data:
            _print(f"Artifact store: ✓ {data['artifact_store']}")
        if "jobs_total" in data:
            _print(f"Jobs: {data['jobs_total']} total")
    except Exception as exc:
        _print(f"Server: {server}")
        _print(f"Status: ✗ unreachable ({exc.__class__.__name__})")


def _start_server(host: str, port: int, reload: bool, workers: int) -> None:
    """Start uvicorn server."""
    try:
        import uvicorn
    except ImportError:
        _print("uvicorn is not installed.")
        _print("Install with: pip install datasphere[api]")
        sys.exit(1)

    _print(f"Starting DataSphere API on http://{host}:{port}...")
    _print("[Ctrl+C to stop]")
    uvicorn.run(
        "datasphere.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# Non-interactive argparse command handlers
# ---------------------------------------------------------------------------

def cmd_generate(args: argparse.Namespace) -> None:
    business_request = args.business_request
    if not business_request:
        business_request = _input("Business request: ").strip()
    if not business_request:
        _print("Error: business request is required.")
        sys.exit(1)

    _print("[Generating...]")

    # Try server first if specified
    result = None
    if getattr(args, "server", None):
        result = _run_generate_with_server(
            server=args.server,
            business_request=business_request,
            cloud=args.cloud,
            warehouse=args.warehouse,
            orchestrator=args.orchestrator,
            budget=args.budget,
        )

    if result is None:
        result = _run_generate_local(
            business_request=business_request,
            cloud=args.cloud,
            warehouse=args.warehouse,
            orchestrator=args.orchestrator,
            budget=args.budget,
        )

    _print(f"✓ Stack: {result.get('stack_summary', 'generated')}")
    _print(f"✓ Estimated cost: ${result.get('estimated_monthly_usd', 0):,}/month")

    warnings = result.get("warnings", [])
    if warnings:
        _print(f"✓ {len(warnings)} warning(s)")
        for w in warnings:
            _print(f"  - {w}")

    output_file = getattr(args, "output", None)
    if output_file:
        with open(output_file, "w") as fh:
            json.dump(result, fh, indent=2)
        _print(f"Saved: {output_file}")


def cmd_templates(args: argparse.Namespace) -> None:
    registry = _get_templates()
    template_id = getattr(args, "template_id", None)
    category = getattr(args, "category", None)

    if template_id:
        t = registry.get(template_id)
        if t:
            _print(_fmt_template_detail(t))
        else:
            _print(f"Template '{template_id}' not found.")
            sys.exit(1)
        return

    if category:
        templates = registry.list_by_category(category)
        if not templates:
            _print(f"No templates found for category '{category}'.")
            return
    else:
        templates = registry.list_all()

    _print(_fmt_templates_table(templates))


def cmd_diff(args: argparse.Namespace) -> None:
    from datasphere.generators.stack_diff import StackDiffGenerator

    from_stack: dict[str, str] = {}
    to_stack: dict[str, str] = {}

    from_file = getattr(args, "from_file", None)
    to_file = getattr(args, "to_file", None)

    if from_file:
        with open(from_file) as fh:
            from_stack = json.load(fh)
    if to_file:
        with open(to_file) as fh:
            to_stack = json.load(fh)

    if not from_stack and not to_stack:
        _print("Provide --from-file and --to-file with JSON stack definitions.")
        _print("Example stack JSON: {\"data_warehouse\": \"redshift\", \"orchestrator\": \"airflow\"}")
        sys.exit(1)

    gen = StackDiffGenerator()
    plan = gen.diff(from_stack, to_stack)
    _print(_fmt_migration_plan(plan))


def cmd_serve(args: argparse.Namespace) -> None:
    _start_server(
        host=args.host,
        port=args.port,
        reload=getattr(args, "reload", False),
        workers=getattr(args, "workers", 1),
    )


def cmd_status(args: argparse.Namespace) -> None:
    server = getattr(args, "server", "http://localhost:8000")
    _check_status(server)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="datasphere",
        description="DataSphere Autonomous Data Platform CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Run without arguments to start the interactive REPL.

            Examples:
              datasphere
              datasphere generate "Pipeline analytics e-commerce" --cloud aws --warehouse snowflake
              datasphere templates
              datasphere templates startup-analytics
              datasphere diff --from-file current.json --to-file target.json
              datasphere serve --port 8000
              datasphere status
        """),
    )
    subparsers = parser.add_subparsers(dest="command")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate a data architecture")
    gen_parser.add_argument("business_request", nargs="?", help="Business description")
    gen_parser.add_argument("--cloud", default="aws", help="Cloud provider (default: aws)")
    gen_parser.add_argument("--warehouse", default="snowflake",
                            help="Data warehouse (default: snowflake)")
    gen_parser.add_argument("--orchestrator", default="airflow",
                            help="Orchestrator (default: airflow)")
    gen_parser.add_argument("--budget", default="medium",
                            choices=["low", "medium", "enterprise"],
                            help="Budget tier (default: medium)")
    gen_parser.add_argument("--output", help="Output file (JSON)")
    gen_parser.add_argument("--server", default="http://localhost:8000",
                            help="API server URL (default: http://localhost:8000)")

    # templates
    tmpl_parser = subparsers.add_parser("templates", help="Browse stack templates")
    tmpl_parser.add_argument("template_id", nargs="?", help="Template ID to show detail")
    tmpl_parser.add_argument("--category", help="Filter by category")

    # diff
    diff_parser = subparsers.add_parser("diff", help="Compare two stacks")
    diff_parser.add_argument("--from-file", dest="from_file",
                             help="JSON file with source stack")
    diff_parser.add_argument("--to-file", dest="to_file",
                             help="JSON file with target stack")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="0.0.0.0",
                              help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000,
                              help="Bind port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true",
                              help="Enable auto-reload (development)")
    serve_parser.add_argument("--workers", type=int, default=1,
                              help="Number of workers (default: 1)")

    # status
    status_parser = subparsers.add_parser("status", help="Check server health")
    status_parser.add_argument("--server", default="http://localhost:8000",
                               help="Server URL (default: http://localhost:8000)")

    # version
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args(argv)

    if args.command is None:
        DataSphereCLI().cmdloop()
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "templates":
        cmd_templates(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "version":
        _print(f"DataSphere v{_VERSION}")


if __name__ == "__main__":
    main()
