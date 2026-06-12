from dataclasses import dataclass, field
from typing import Any


@dataclass
class StackChange:
    component: str
    from_tool: str
    to_tool: str
    change_type: str  # "upgrade", "replace", "add", "remove", "no_change"
    effort: str       # "low", "medium", "high"
    risk: str         # "low", "medium", "high"
    migration_steps: list[str]
    estimated_days: int


@dataclass
class MigrationPlan:
    changes: list[StackChange]
    total_estimated_days: int
    overall_risk: str        # "low", "medium", "high"
    migration_order: list[str]
    rollback_strategy: str
    summary: str


# ---------------------------------------------------------------------------
# Migration knowledge base
# ---------------------------------------------------------------------------

_DEFAULT_STEPS = [
    "Evaluate compatibility",
    "Plan migration",
    "Execute migration",
    "Validate",
    "Cutover",
]

_MIGRATION_KB: dict[tuple[str, str], dict] = {
    # Orchestration
    ("airflow", "dagster"): {
        "effort": "high",
        "risk": "medium",
        "days": 20,
        "steps": [
            "Audit existing DAGs",
            "Map Airflow operators to Dagster ops",
            "Rewrite pipelines as Dagster jobs/assets",
            "Set up Dagster deployment",
            "Parallel run period (2 weeks)",
            "Cut over and decommission Airflow",
        ],
    },
    ("airflow", "prefect"): {
        "effort": "medium",
        "risk": "low",
        "days": 14,
        "steps": _DEFAULT_STEPS,
    },
    ("dagster", "airflow"): {
        "effort": "high",
        "risk": "medium",
        "days": 25,
        "steps": _DEFAULT_STEPS,
    },
    ("prefect", "airflow"): {
        "effort": "medium",
        "risk": "medium",
        "days": 15,
        "steps": _DEFAULT_STEPS,
    },
    # Warehouse
    ("redshift", "snowflake"): {
        "effort": "high",
        "risk": "high",
        "days": 30,
        "steps": [
            "Export schemas from Redshift",
            "Convert Redshift SQL to Snowflake SQL",
            "Set up Snowflake account and warehouses",
            "Migrate historical data with AWS DMS or custom scripts",
            "Update dbt profiles.yml",
            "Validate data with row counts + checksums",
            "Update ingestion connectors",
            "Cut over in maintenance window",
            "Monitor for 2 weeks",
            "Decommission Redshift",
        ],
    },
    ("postgresql", "snowflake"): {
        "effort": "medium",
        "risk": "medium",
        "days": 20,
        "steps": _DEFAULT_STEPS,
    },
    ("snowflake", "bigquery"): {
        "effort": "high",
        "risk": "high",
        "days": 25,
        "steps": _DEFAULT_STEPS,
    },
    ("bigquery", "snowflake"): {
        "effort": "medium",
        "risk": "medium",
        "days": 20,
        "steps": _DEFAULT_STEPS,
    },
    ("redshift", "bigquery"): {
        "effort": "high",
        "risk": "high",
        "days": 35,
        "steps": _DEFAULT_STEPS,
    },
    # Ingestion
    ("fivetran", "airbyte"): {
        "effort": "medium",
        "risk": "low",
        "days": 10,
        "steps": [
            "Inventory all Fivetran connectors",
            "Check Airbyte connector availability",
            "Deploy Airbyte (Docker or Cloud)",
            "Configure equivalent connectors",
            "Parallel sync validation",
            "Cut over",
            "Cancel Fivetran subscription",
        ],
    },
    ("airbyte", "fivetran"): {
        "effort": "low",
        "risk": "low",
        "days": 7,
        "steps": _DEFAULT_STEPS,
    },
    ("meltano", "airbyte"): {
        "effort": "medium",
        "risk": "low",
        "days": 8,
        "steps": _DEFAULT_STEPS,
    },
    # BI
    ("tableau", "metabase"): {
        "effort": "medium",
        "risk": "low",
        "days": 15,
        "steps": _DEFAULT_STEPS,
    },
    ("tableau", "superset"): {
        "effort": "medium",
        "risk": "medium",
        "days": 20,
        "steps": _DEFAULT_STEPS,
    },
    ("looker", "metabase"): {
        "effort": "high",
        "risk": "medium",
        "days": 25,
        "steps": _DEFAULT_STEPS,
    },
    ("metabase", "superset"): {
        "effort": "low",
        "risk": "low",
        "days": 5,
        "steps": _DEFAULT_STEPS,
    },
}

# "any → duckdb" special rule
_DUCKDB_WARNING = "WARNING: duckdb is only recommended for dev/analytics workloads, not production pipelines."

# Canonical migration order
_MIGRATION_ORDER = [
    "data_warehouse",
    "ingestion",
    "transformation",
    "orchestrator",
    "quality",
    "catalog",
    "bi_tool",
]


def _lookup(from_tool: str, to_tool: str) -> dict:
    key = (from_tool.lower(), to_tool.lower())
    if key in _MIGRATION_KB:
        return dict(_MIGRATION_KB[key])
    if to_tool.lower() == "duckdb":
        return {
            "effort": "low",
            "risk": "low",
            "days": 5,
            "steps": [
                _DUCKDB_WARNING,
                "Install DuckDB",
                "Export data from source warehouse",
                "Import into DuckDB",
                "Validate queries",
                "Update connection strings",
            ],
        }
    return {
        "effort": "medium",
        "risk": "medium",
        "days": 10,
        "steps": list(_DEFAULT_STEPS),
    }


def _overall_risk(changes: list[StackChange]) -> str:
    risks = [c.risk for c in changes]
    if "high" in risks:
        return "high"
    if "medium" in risks:
        return "medium"
    return "low"


def _build_rollback_strategy(changes: list[StackChange]) -> str:
    parts = []
    for c in changes:
        if c.change_type == "remove":
            parts.append(f"Keep {c.from_tool} available for fallback until migration is fully validated.")
        elif c.change_type in ("replace", "upgrade"):
            if c.component == "orchestrator":
                parts.append(
                    f"Keep old {c.from_tool} deployment running in parallel for 2 weeks before decommissioning."
                )
            elif c.component == "data_warehouse":
                parts.append(
                    f"Maintain {c.from_tool} snapshots for 30 days."
                )
            else:
                parts.append(
                    f"Maintain {c.from_tool} in standby for {c.estimated_days} days post-cutover."
                )
    if not parts:
        return "No rollback required — no breaking changes detected."
    return " ".join(parts)


def _build_summary(changes: list[StackChange], total_days: int, risk: str) -> str:
    if not changes:
        return "No migration required — stacks are identical."
    replacements = [c for c in changes if c.change_type in ("replace", "upgrade")]
    if replacements:
        pairs = " + ".join(f"{c.from_tool} → {c.to_tool}" for c in replacements[:3])
        return (
            f"Migration {pairs} — {risk} complexity, ~{total_days} days estimated."
        )
    adds = [c.to_tool for c in changes if c.change_type == "add"]
    removes = [c.from_tool for c in changes if c.change_type == "remove"]
    parts = []
    if adds:
        parts.append(f"Adding {', '.join(adds)}")
    if removes:
        parts.append(f"Removing {', '.join(removes)}")
    return f"{'; '.join(parts)} — {risk} risk, ~{total_days} days."


class StackDiffGenerator:
    def diff(self, from_stack: dict, to_stack: dict) -> MigrationPlan:
        """Compare two stacks and generate a migration plan."""
        all_components = set(from_stack) | set(to_stack)
        changes: list[StackChange] = []

        for component in all_components:
            from_tool = from_stack.get(component, "")
            to_tool = to_stack.get(component, "")

            if not from_tool and to_tool:
                # New component added
                changes.append(StackChange(
                    component=component,
                    from_tool="",
                    to_tool=to_tool,
                    change_type="add",
                    effort="low",
                    risk="low",
                    migration_steps=[f"Deploy {to_tool}", "Configure integration", "Validate"],
                    estimated_days=3,
                ))
            elif from_tool and not to_tool:
                # Component removed
                changes.append(StackChange(
                    component=component,
                    from_tool=from_tool,
                    to_tool="",
                    change_type="remove",
                    effort="low",
                    risk="low",
                    migration_steps=[f"Migrate workloads off {from_tool}", f"Decommission {from_tool}"],
                    estimated_days=2,
                ))
            elif from_tool and to_tool:
                if from_tool.lower() == to_tool.lower():
                    # No change — skip
                    continue
                kb = _lookup(from_tool, to_tool)
                changes.append(StackChange(
                    component=component,
                    from_tool=from_tool,
                    to_tool=to_tool,
                    change_type="replace",
                    effort=kb["effort"],
                    risk=kb["risk"],
                    migration_steps=kb["steps"],
                    estimated_days=kb["days"],
                ))

        total_days = sum(c.estimated_days for c in changes)
        risk = _overall_risk(changes)

        # Build ordered migration list (only components present in changes)
        changed_components = {c.component for c in changes}
        migration_order = [c for c in _MIGRATION_ORDER if c in changed_components]
        # Append any unknown components not in canonical order
        for comp in changed_components:
            if comp not in migration_order:
                migration_order.append(comp)

        rollback = _build_rollback_strategy(changes)
        summary = _build_summary(changes, total_days, risk)

        return MigrationPlan(
            changes=changes,
            total_estimated_days=total_days,
            overall_risk=risk,
            migration_order=migration_order,
            rollback_strategy=rollback,
            summary=summary,
        )
