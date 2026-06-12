"""Static pricing tables for cloud data platform cost estimation."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# AWS RDS / Redshift / EC2 (USD/month)
AWS_WAREHOUSE_COSTS = {
    "redshift":   {"low": 180,  "medium": 720,   "enterprise": 4800},
    "postgresql": {"low": 50,   "medium": 200,   "enterprise": 1200},
    "mysql":      {"low": 40,   "medium": 180,   "enterprise": 1000},
}

# Snowflake (credits/month x $3/credit)
SNOWFLAKE_COSTS = {
    "low":        150,   # XS warehouse, light usage
    "medium":     800,   # S warehouse, moderate
    "enterprise": 4500,  # M warehouse, heavy
}

# BigQuery (storage + compute, USD/month)
BIGQUERY_COSTS = {
    "low":        80,
    "medium":     400,
    "enterprise": 2500,
}

# ClickHouse Cloud (USD/month)
CLICKHOUSE_COSTS = {
    "low":        0,
    "medium":     200,
    "enterprise": 1200,
}

# DuckDB (embedded, no cloud cost)
DUCKDB_COSTS = {
    "low":        0,
    "medium":     0,
    "enterprise": 0,
}

# Azure Synapse (USD/month)
SYNAPSE_COSTS = {
    "low":        150,
    "medium":     600,
    "enterprise": 3500,
}

# Databricks (USD/month)
DATABRICKS_COSTS = {
    "low":        300,
    "medium":     900,
    "enterprise": 4000,
}

# Orchestration costs
ORCHESTRATION_COSTS = {
    "airflow":  {"low": 0,   "medium": 150, "enterprise": 500},   # MWAA pricing
    "dagster":  {"low": 0,   "medium": 200, "enterprise": 600},
    "prefect":  {"low": 0,   "medium": 100, "enterprise": 400},
    "argo":     {"low": 0,   "medium": 0,   "enterprise": 100},
    "kestra":   {"low": 0,   "medium": 50,  "enterprise": 200},
}

# Ingestion costs
INGESTION_COSTS = {
    "airbyte":       {"low": 0,   "medium": 300,  "enterprise": 1000},  # Cloud pricing
    "fivetran":      {"low": 100, "medium": 500,  "enterprise": 2000},
    "meltano":       {"low": 0,   "medium": 50,   "enterprise": 200},
    "kafka-connect": {"low": 50,  "medium": 300,  "enterprise": 1500},
    "debezium":      {"low": 0,   "medium": 80,   "enterprise": 400},
}

# Cloud infrastructure base cost (networking, K8s, storage)
CLOUD_BASE_COSTS = {
    "aws":   {"low": 80,  "medium": 300,  "enterprise": 1500},
    "gcp":   {"low": 70,  "medium": 250,  "enterprise": 1200},
    "azure": {"low": 90,  "medium": 320,  "enterprise": 1600},
    "other": {"low": 20,  "medium": 80,   "enterprise": 400},
}

# BI tool costs
BI_COSTS = {
    "metabase": {"low": 0,    "medium": 100,  "enterprise": 500},
    "superset": {"low": 0,    "medium": 50,   "enterprise": 200},
    "tableau":  {"low": 420,  "medium": 840,  "enterprise": 3000},
    "looker":   {"low": 3000, "medium": 5000, "enterprise": 15000},
    "redash":   {"low": 0,    "medium": 50,   "enterprise": 200},
    "grafana":  {"low": 0,    "medium": 100,  "enterprise": 400},
    "powerbi":  {"low": 10,   "medium": 100,  "enterprise": 1000},
    "evidence": {"low": 0,    "medium": 0,    "enterprise": 0},
}

# Master lookup: warehouse tool -> cost tiers
WAREHOUSE_COSTS: dict[str, dict[str, float]] = {
    "snowflake":     SNOWFLAKE_COSTS,
    "bigquery":      BIGQUERY_COSTS,
    "redshift":      AWS_WAREHOUSE_COSTS["redshift"],
    "postgresql":    AWS_WAREHOUSE_COSTS["postgresql"],
    "mysql":         AWS_WAREHOUSE_COSTS["mysql"],
    "clickhouse":    CLICKHOUSE_COSTS,
    "duckdb":        DUCKDB_COSTS,
    "azure-synapse": SYNAPSE_COSTS,
    "databricks":    DATABRICKS_COSTS,
}

# Transformation costs
TRANSFORMATION_COSTS: dict[str, dict[str, float]] = {
    "dbt":     {"low": 0,   "medium": 0,   "enterprise": 100},
    "sqlmesh": {"low": 0,   "medium": 0,   "enterprise": 50},
    "spark":   {"low": 100, "medium": 400, "enterprise": 1500},
    "flink":   {"low": 150, "medium": 500, "enterprise": 2000},
    "polars":  {"low": 0,   "medium": 0,   "enterprise": 0},
}

# Quality / catalog costs
QUALITY_COSTS: dict[str, dict[str, float]] = {
    "great-expectations": {"low": 0, "medium": 0,   "enterprise": 50},
    "soda-core":          {"low": 0, "medium": 50,  "enterprise": 200},
    "dbt-tests":          {"low": 0, "medium": 0,   "enterprise": 0},
}

CATALOG_COSTS: dict[str, dict[str, float]] = {
    "openmetadata": {"low": 0, "medium": 30,  "enterprise": 150},
    "datahub":      {"low": 0, "medium": 50,  "enterprise": 200},
    "amundsen":     {"low": 0, "medium": 30,  "enterprise": 100},
    "marquez":      {"low": 0, "medium": 0,   "enterprise": 30},
}


# ---------------------------------------------------------------------------
# CostBreakdown dataclass
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    component: str
    tool: str
    monthly_usd: float
    yearly_usd: float
    notes: str = ""


@dataclass
class CostBreakdown:
    line_items: list[LineItem] = field(default_factory=list)
    total_monthly_usd: float = 0.0
    total_yearly_usd: float = 0.0
    budget_tier: str = "medium"
    savings_tips: list[str] = field(default_factory=list)
    comparison: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CostCalculator
# ---------------------------------------------------------------------------

# Cloud-specific multipliers for warehouse costs
_CLOUD_WAREHOUSE_MULT = {
    "aws":   1.0,
    "gcp":   0.92,   # GCP/BigQuery slightly cheaper on average
    "azure": 1.05,
    "other": 0.8,
}

_SAVINGS_TRIGGERS = [
    ("fivetran",      "airbyte",   "Fivetran adds ${cost}/mo — consider Airbyte (open-source, free tier) for up to 80% savings"),
    ("tableau",       "metabase",  "Tableau adds ${cost}/mo — Metabase or Superset are free alternatives"),
    ("looker",        "superset",  "Looker license is ${cost}/mo — consider Superset for ~95% savings"),
    ("databricks",    "spark",     "Databricks adds ${cost}/mo — self-hosted Spark can reduce costs significantly"),
    ("azure-synapse", "postgresql","Azure Synapse adds ${cost}/mo — PostgreSQL is free for low/medium workloads"),
    ("powerbi",       "superset",  "Power BI adds ${cost}/mo — Superset is a free open-source alternative"),
]


def _lookup(table: dict, tool: str, budget: str) -> tuple[float, str]:
    """Return (cost, notes) for a tool. Returns (0, 'unknown') if not found."""
    t = table.get(tool)
    if t is None:
        return 0.0, "unknown tool — cost not estimated"
    cost = float(t.get(budget, 0))
    return cost, ""


class CostCalculator:
    """Calculate detailed cost breakdown for a data platform stack."""

    def calculate(self, stack: dict, budget: str = "medium") -> CostBreakdown:
        """
        Calculate detailed cost breakdown for a stack.

        Parameters
        ----------
        stack : dict
            validated_stack dict with keys like data_warehouse, ingestion, etc.
        budget : str
            One of 'low', 'medium', 'enterprise'

        Returns
        -------
        CostBreakdown with line_items, totals, savings_tips and multi-cloud comparison
        """
        if budget not in ("low", "medium", "enterprise"):
            budget = "medium"

        cloud = (stack.get("cloud_provider") or "aws").lower()
        line_items: list[LineItem] = []

        def add_item(component: str, tool: str, table: dict, notes: str = "") -> float:
            tool_key = tool.lower().replace(" ", "-") if tool else ""
            cost, auto_note = _lookup(table, tool_key, budget)
            final_notes = notes or auto_note
            if not final_notes and cost == 0:
                final_notes = "open-source — infrastructure cost only"
            item = LineItem(
                component=component,
                tool=tool or "none",
                monthly_usd=round(cost, 2),
                yearly_usd=round(cost * 12, 2),
                notes=final_notes,
            )
            line_items.append(item)
            return cost

        total = 0.0

        # Warehouse
        wh = stack.get("data_warehouse") or ""
        wh_key = wh.lower().replace(" ", "-")
        wh_cost, _ = _lookup(WAREHOUSE_COSTS, wh_key, budget)
        wh_notes = f"{budget} tier, {cloud} region" if wh_cost > 0 else "open-source"
        line_items.append(LineItem(
            component="warehouse", tool=wh or "none",
            monthly_usd=round(wh_cost, 2), yearly_usd=round(wh_cost * 12, 2),
            notes=wh_notes,
        ))
        total += wh_cost

        # Ingestion
        ing = stack.get("ingestion") or ""
        total += add_item("ingestion", ing, INGESTION_COSTS)

        # Orchestration
        orch = stack.get("orchestrator") or stack.get("orchestration") or ""
        total += add_item("orchestration", orch, ORCHESTRATION_COSTS)

        # Transformation
        transf = stack.get("transformation") or ""
        total += add_item("transformation", transf, TRANSFORMATION_COSTS)

        # BI
        bi = stack.get("bi_tool") or stack.get("bi") or ""
        bi_key = bi.lower().replace(" ", "-") if bi else ""
        bi_cost, _ = _lookup(BI_COSTS, bi_key, budget)
        bi_notes = "license per user" if bi_key in ("tableau", "looker", "powerbi") else ""
        line_items.append(LineItem(
            component="bi", tool=bi or "none",
            monthly_usd=round(bi_cost, 2), yearly_usd=round(bi_cost * 12, 2),
            notes=bi_notes,
        ))
        total += bi_cost

        # Quality
        quality = stack.get("quality") or ""
        total += add_item("quality", quality, QUALITY_COSTS)

        # Catalog
        catalog = stack.get("catalog") or ""
        total += add_item("catalog", catalog, CATALOG_COSTS)

        # Cloud base (infra, networking, K8s)
        cloud_key = cloud if cloud in CLOUD_BASE_COSTS else "other"
        base_cost, _ = _lookup(CLOUD_BASE_COSTS, cloud_key, budget)
        line_items.append(LineItem(
            component="infrastructure", tool=cloud_key,
            monthly_usd=round(base_cost, 2), yearly_usd=round(base_cost * 12, 2),
            notes="networking, K8s/compute base cost",
        ))
        total += base_cost

        total = round(total, 2)

        # Multi-cloud comparison
        comparison = self._cloud_comparison(stack, budget, total, cloud)

        # Savings tips
        savings_tips = self._savings_tips(stack, budget)

        return CostBreakdown(
            line_items=line_items,
            total_monthly_usd=total,
            total_yearly_usd=round(total * 12, 2),
            budget_tier=budget,
            savings_tips=savings_tips,
            comparison=comparison,
        )

    def _cloud_comparison(self, stack: dict, budget: str, base_total: float, current_cloud: str) -> dict[str, float]:
        """Estimate the same stack on all 3 clouds."""
        result: dict[str, float] = {}
        current_base = CLOUD_BASE_COSTS.get(current_cloud, CLOUD_BASE_COSTS["other"]).get(budget, 0)

        for cloud in ("aws", "gcp", "azure"):
            other_base = CLOUD_BASE_COSTS[cloud].get(budget, 0)
            # Replace current cloud infra cost with target cloud
            adjusted = base_total - current_base + other_base

            # Warehouse cost may differ by cloud (e.g. BigQuery on GCP)
            wh = (stack.get("data_warehouse") or "").lower().replace(" ", "-")
            if wh == "bigquery":
                # BigQuery is native to GCP; on AWS/Azure approximate with Redshift/Synapse
                native_cost = float(BIGQUERY_COSTS.get(budget, 0))
                wh_cost = float(WAREHOUSE_COSTS.get(wh, {}).get(budget, 0))
                if cloud == "gcp":
                    adjusted = adjusted  # already using BigQuery cost
                else:
                    # Substitute with redshift/synapse
                    alt = "redshift" if cloud == "aws" else "azure-synapse"
                    alt_cost = float(WAREHOUSE_COSTS.get(alt, {}).get(budget, 0))
                    adjusted = adjusted - native_cost + alt_cost
            elif wh == "redshift":
                native_cost = float(WAREHOUSE_COSTS.get(wh, {}).get(budget, 0))
                if cloud == "aws":
                    pass
                elif cloud == "gcp":
                    alt_cost = float(BIGQUERY_COSTS.get(budget, 0))
                    adjusted = adjusted - native_cost + alt_cost
                else:
                    alt_cost = float(SYNAPSE_COSTS.get(budget, 0))
                    adjusted = adjusted - native_cost + alt_cost
            elif wh == "azure-synapse":
                native_cost = float(WAREHOUSE_COSTS.get(wh, {}).get(budget, 0))
                if cloud == "azure":
                    pass
                elif cloud == "aws":
                    alt_cost = float(WAREHOUSE_COSTS.get("redshift", {}).get(budget, 0))
                    adjusted = adjusted - native_cost + alt_cost
                else:
                    alt_cost = float(BIGQUERY_COSTS.get(budget, 0))
                    adjusted = adjusted - native_cost + alt_cost

            result[cloud] = round(adjusted, 2)
        return result

    def _savings_tips(self, stack: dict, budget: str) -> list[str]:
        """Generate actionable savings tips based on the stack."""
        tips: list[str] = []
        # Build normalized tool list
        tools = set()
        for v in stack.values():
            if isinstance(v, str):
                tools.add(v.lower().replace(" ", "-"))

        for expensive, cheap, template in _SAVINGS_TRIGGERS:
            if expensive in tools:
                # Find cost
                cost_table = {
                    **{k: v for k, v in INGESTION_COSTS.items()},
                    **{k: v for k, v in BI_COSTS.items()},
                    **{k: v for k, v in WAREHOUSE_COSTS.items()},
                }
                cost = cost_table.get(expensive, {}).get(budget, 0)
                if cost > 0:
                    tip = template.replace("${cost}", f"${cost:,}")
                    tips.append(tip)

        # DuckDB tip for low workloads
        wh = (stack.get("data_warehouse") or "").lower()
        if wh in ("snowflake", "bigquery", "redshift") and budget == "low":
            wh_cost = WAREHOUSE_COSTS.get(wh, {}).get("low", 0)
            tips.append(
                f"For low traffic, DuckDB is free vs {wh.title()} at ${wh_cost}/mo"
            )

        # Enterprise negotiation tip
        if budget == "enterprise":
            tips.append(
                "At enterprise scale, negotiate annual contracts with SaaS vendors (Snowflake, Fivetran) for 20-40% discounts"
            )

        return tips
