from __future__ import annotations
from datasphere.agents.base_agent import BaseAgent
from datasphere.models.request import BusinessRequest
from datasphere.models.output import AgentOutput, CostOptimizationOutput, CostEstimate

# Monthly USD estimates per tool/tier (medium volume baseline)
COST_TABLE: dict[str, dict[str, float]] = {
    # Warehouses
    "snowflake":     {"low": 150,  "medium": 500,   "enterprise": 2000},
    "bigquery":      {"low": 50,   "medium": 200,   "enterprise": 800},
    "redshift":      {"low": 200,  "medium": 600,   "enterprise": 2500},
    "azure-synapse": {"low": 180,  "medium": 550,   "enterprise": 2200},
    "databricks":    {"low": 300,  "medium": 900,   "enterprise": 4000},
    "postgresql":    {"low": 0,    "medium": 50,    "enterprise": 200},
    "clickhouse":    {"low": 0,    "medium": 80,    "enterprise": 300},
    "duckdb":        {"low": 0,    "medium": 0,     "enterprise": 0},
    # Ingestion
    "airbyte":       {"low": 0,    "medium": 100,   "enterprise": 500},
    "meltano":       {"low": 0,    "medium": 0,     "enterprise": 50},
    "kafka-connect": {"low": 0,    "medium": 150,   "enterprise": 600},
    "debezium":      {"low": 0,    "medium": 50,    "enterprise": 200},
    "fivetran-like": {"low": 300,  "medium": 1000,  "enterprise": 5000},
    # Orchestration
    "airflow":       {"low": 0,    "medium": 80,    "enterprise": 300},
    "dagster":       {"low": 0,    "medium": 80,    "enterprise": 300},
    "prefect":       {"low": 0,    "medium": 100,   "enterprise": 400},
    "argo":          {"low": 0,    "medium": 0,     "enterprise": 100},
    "kestra":        {"low": 0,    "medium": 50,    "enterprise": 200},
    # Transformation
    "dbt":           {"low": 0,    "medium": 0,     "enterprise": 100},
    "sqlmesh":       {"low": 0,    "medium": 0,     "enterprise": 50},
    "spark":         {"low": 100,  "medium": 400,   "enterprise": 1500},
    "flink":         {"low": 150,  "medium": 500,   "enterprise": 2000},
    "polars":        {"low": 0,    "medium": 0,     "enterprise": 0},
    # Storage
    "s3":            {"low": 5,    "medium": 50,    "enterprise": 300},
    "adls":          {"low": 5,    "medium": 50,    "enterprise": 300},
    "gcs":           {"low": 5,    "medium": 50,    "enterprise": 300},
    "minio":         {"low": 0,    "medium": 20,    "enterprise": 80},
    # BI
    "superset":      {"low": 0,    "medium": 0,     "enterprise": 100},
    "metabase":      {"low": 0,    "medium": 50,    "enterprise": 200},
    "grafana":       {"low": 0,    "medium": 0,     "enterprise": 50},
    "powerbi":       {"low": 10,   "medium": 100,   "enterprise": 1000},
    "tableau":       {"low": 70,   "medium": 500,   "enterprise": 3000},
    "evidence":      {"low": 0,    "medium": 0,     "enterprise": 0},
    "redash":        {"low": 0,    "medium": 0,     "enterprise": 50},
    # Quality / Catalog
    "great-expectations": {"low": 0, "medium": 0,  "enterprise": 50},
    "soda-core":     {"low": 0,    "medium": 50,    "enterprise": 200},
    "dbt-tests":     {"low": 0,    "medium": 0,     "enterprise": 0},
    "openmetadata":  {"low": 0,    "medium": 30,    "enterprise": 150},
    "datahub":       {"low": 0,    "medium": 50,    "enterprise": 200},
    "amundsen":      {"low": 0,    "medium": 30,    "enterprise": 100},
    "marquez":       {"low": 0,    "medium": 0,     "enterprise": 30},
    # Security
    "vault":         {"low": 0,    "medium": 20,    "enterprise": 200},
    "keycloak":      {"low": 0,    "medium": 20,    "enterprise": 100},
    # Infrastructure / compute overhead
    "kubernetes":    {"low": 100,  "medium": 400,   "enterprise": 2000},
    "docker-compose":{"low": 0,    "medium": 0,     "enterprise": 0},
    "terraform":     {"low": 0,    "medium": 0,     "enterprise": 0},
    # Monitoring
    "prometheus":    {"low": 0,    "medium": 0,     "enterprise": 50},
    "grafana":       {"low": 0,    "medium": 0,     "enterprise": 50},
    "opentelemetry": {"low": 0,    "medium": 20,    "enterprise": 100},
}

OPEN_SOURCE_ALTERNATIVES: dict[str, str] = {
    "snowflake":   "postgresql",
    "databricks":  "spark",
    "fivetran-like": "airbyte",
    "tableau":     "superset",
    "powerbi":     "superset",
    "flink":       "kafka-connect",
}

SAVINGS_TIPS: dict[str, str] = {
    "aws": (
        "Utilisez des instances Spot/Reserved pour EKS et EC2 (-60%). "
        "Activez S3 Intelligent Tiering. "
        "Redshift Serverless pour les workloads intermittents."
    ),
    "azure": (
        "Azure Reserved Instances (-40%). "
        "Synapse Serverless SQL pour les requêtes ad-hoc. "
        "ADLS lifecycle policies pour archivage automatique."
    ),
    "gcp": (
        "BigQuery slots reservations pour les charges prévisibles. "
        "GCS Nearline/Coldline pour les données froides. "
        "Committed Use Discounts sur GKE (-30%)."
    ),
    "local-docker": (
        "Coûts quasi nuls — uniquement infrastructure hardware. "
        "Optimisez le sizing des containers."
    ),
    "kubernetes": (
        "VPA (Vertical Pod Autoscaler) pour right-sizing. "
        "Node auto-provisioning pour scale-to-zero. "
        "Cluster autoscaler pour les nœuds."
    ),
}


class CostOptimizationAgent(BaseAgent):
    name = "cost-optimization"
    description = "Estime les coûts mensuels et propose des optimisations."

    def _run(self, request: BusinessRequest, context: dict) -> CostOptimizationOutput:
        c = self._constraints(request)
        budget = c.budget

        tools = {
            "Warehouse":      c.data_warehouse,
            "Ingestion":      c.ingestion,
            "Orchestration":  c.orchestrator,
            "Transformation": c.transformation,
            "Storage":        c.data_lake or "minio",
            "BI":             c.bi_tool,
            "Quality":        c.quality or "great-expectations",
            "Catalog":        c.catalog or "openmetadata",
            "Infrastructure": c.deployment.lower().replace(" ", "-"),
        }

        estimates: list[CostEstimate] = []
        total = 0.0

        for layer, tool in tools.items():
            tool_key = tool.lower().replace(" ", "-")
            costs = COST_TABLE.get(tool_key, {})
            cost = costs.get(budget, 0.0)

            # Volume multiplier
            vol_mult = {"small": 0.5, "medium": 1.0, "large": 2.5, "xlarge": 8.0}.get(c.data_volume, 1.0)
            # Realtime adds ~40%
            if c.processing_mode == "realtime" and layer in ("Ingestion", "Transformation"):
                vol_mult *= 1.4

            final = round(cost * vol_mult, 2)
            total += final

            note = self._cost_note(tool_key, c.cloud_provider, budget, cost)
            estimates.append(CostEstimate(
                service=f"{layer}: {tool}",
                monthly_usd=final,
                tier=budget,
                notes=note,
            ))

        # Optimizations
        optimizations = []
        alternative_stack: dict[str, str] | None = None
        savings = 0.0

        for tool, alt in OPEN_SOURCE_ALTERNATIVES.items():
            if tool in tools.values():
                tool_cost = COST_TABLE.get(tool, {}).get(budget, 0)
                alt_cost = COST_TABLE.get(alt, {}).get(budget, 0)
                saving = round((tool_cost - alt_cost), 2)
                if saving > 0:
                    optimizations.append(
                        f"Remplacez {tool} par {alt} → économie estimée : ${saving}/mois"
                    )
                    savings += saving
                    if alternative_stack is None:
                        alternative_stack = {}
                    for layer, t in tools.items():
                        if t.lower().replace(" ", "-") == tool:
                            alternative_stack[layer] = alt

        cloud_tip = SAVINGS_TIPS.get(c.cloud_provider, "")
        if cloud_tip:
            optimizations.append(f"Optimisations {c.cloud_provider}: {cloud_tip}")

        if c.budget == "enterprise" and total > 5000:
            optimizations.append(
                "Coût mensuel > 5000$ : négociez des contrats annuels avec vos fournisseurs SaaS (Snowflake, Airbyte) pour -20% à -40%."
            )

        output = CostOptimizationOutput(
            estimates=estimates,
            total_monthly_usd=round(total, 2),
            total_yearly_usd=round(total * 12, 2),
            optimizations=optimizations,
            alternative_stack=alternative_stack,
            savings_usd=round(savings, 2),
        )
        output.artifacts["cost_report.md"] = self._render(request, estimates, total, optimizations, savings)
        return output

    def _cost_note(self, tool: str, cloud: str, budget: str, cost: float) -> str:
        if cost == 0:
            return "Open-source — coût infrastructure uniquement"
        if tool in ("snowflake", "bigquery", "redshift", "azure-synapse"):
            return f"Coût compute + stockage ({budget} tier, région {cloud})"
        if tool in ("tableau", "powerbi"):
            return "Licence par utilisateur incluse"
        return f"Estimation {budget} tier"

    def _render(
        self, request: BusinessRequest, estimates: list[CostEstimate],
        total: float, optimizations: list[str], savings: float
    ) -> str:
        c = request.architecture_constraints
        lines = [
            f"# Cost Report — {request.business_request}",
            "",
            f"**Cloud:** {c.cloud_provider}  |  **Volume:** {c.data_volume}  "
            f"|  **Mode:** {c.processing_mode}  |  **Budget:** {c.budget}",
            "",
            "## Estimation mensuelle",
            "",
            "| Service | Outil | Coût/mois (USD) | Notes |",
            "|---------|-------|-----------------|-------|",
        ]
        for e in estimates:
            lines.append(f"| {e.service} | | ${e.monthly_usd:,.2f} | {e.notes} |")
        lines += [
            f"| **TOTAL** | | **${total:,.2f}** | |",
            f"| **TOTAL annuel** | | **${total * 12:,.2f}** | |",
            "",
            "## Optimisations recommandées",
            "",
        ]
        for opt in optimizations:
            lines.append(f"- {opt}")
        if savings > 0:
            lines += [
                "",
                f"**Économie potentielle avec stack open-source : ${savings:,.2f}/mois "
                f"(${savings * 12:,.2f}/an)**",
            ]
        return "\n".join(lines)
