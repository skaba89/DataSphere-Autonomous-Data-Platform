from __future__ import annotations
from datasphere.agents.base_agent import BaseAgent
from datasphere.models.request import BusinessRequest
from datasphere.models.output import AgentOutput, StackAdvisorOutput

# Compatibility rules: (tool_a, tool_b) -> True if compatible
COMPAT: dict[tuple[str, str], bool] = {
    ("dbt", "snowflake"): True,
    ("dbt", "bigquery"): True,
    ("dbt", "redshift"): True,
    ("dbt", "postgresql"): True,
    ("dbt", "clickhouse"): True,
    ("dbt", "azure-synapse"): True,
    ("dbt", "databricks"): True,
    ("dbt", "duckdb"): True,
    ("sqlmesh", "postgresql"): True,
    ("sqlmesh", "snowflake"): True,
    ("sqlmesh", "bigquery"): True,
    ("sqlmesh", "duckdb"): True,
    ("spark", "databricks"): True,
    ("spark", "s3"): True,
    ("spark", "adls"): True,
    ("spark", "gcs"): True,
    ("flink", "kafka-connect"): True,
    ("flink", "debezium"): True,
    ("airflow", "dbt"): True,
    ("dagster", "dbt"): True,
    ("prefect", "dbt"): True,
    ("argo", "dbt"): True,
    ("airbyte", "snowflake"): True,
    ("airbyte", "bigquery"): True,
    ("airbyte", "redshift"): True,
    ("airbyte", "postgresql"): True,
    ("meltano", "postgresql"): True,
    ("meltano", "snowflake"): True,
    ("meltano", "bigquery"): True,
}

ALTERNATIVES: dict[str, list[str]] = {
    "warehouse": ["postgresql", "clickhouse", "duckdb", "snowflake", "bigquery", "redshift"],
    "orchestration": ["airflow", "dagster", "prefect", "argo", "kestra"],
    "ingestion": ["airbyte", "meltano", "kafka-connect", "debezium"],
    "transformation": ["dbt", "sqlmesh", "spark", "polars"],
    "bi": ["superset", "metabase", "grafana", "evidence", "redash"],
    "quality": ["great-expectations", "soda-core", "dbt-tests", "deequ"],
    "catalog": ["openmetadata", "datahub", "amundsen", "marquez"],
}

MATURITY: dict[str, int] = {
    "airflow": 5, "dbt": 5, "postgresql": 5, "snowflake": 5,
    "airbyte": 4, "superset": 4, "dagster": 4, "prefect": 4,
    "great-expectations": 4, "openmetadata": 3, "datahub": 4,
    "sqlmesh": 3, "soda-core": 3, "meltano": 3,
    "clickhouse": 4, "bigquery": 5, "redshift": 5,
    "flink": 4, "spark": 5, "kafka-connect": 4, "debezium": 4,
}

VOLUME_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "small": {
        "warehouse": "duckdb ou postgresql — overhead minimal",
        "transformation": "dbt ou polars — pas besoin de Spark",
        "ingestion": "meltano — léger, Singer-based",
    },
    "medium": {
        "warehouse": "postgresql, clickhouse ou snowflake",
        "transformation": "dbt — standard industrie",
        "ingestion": "airbyte — 300+ connecteurs",
    },
    "large": {
        "warehouse": "snowflake, bigquery ou redshift — auto-scaling",
        "transformation": "dbt + matérialisation incrémentale",
        "ingestion": "airbyte ou kafka-connect",
    },
    "xlarge": {
        "warehouse": "snowflake, databricks ou bigquery — séparation compute/storage",
        "transformation": "spark ou flink — distribué",
        "ingestion": "kafka-connect ou debezium — streaming",
    },
}


class StackAdvisorAgent(BaseAgent):
    name = "stack-advisor"
    description = "Valide la cohérence de la stack, détecte les incompatibilités et propose des alternatives."

    def _run(self, request: BusinessRequest, context: dict) -> StackAdvisorOutput:
        c = self._constraints(request)
        warnings: list[str] = []
        compatibility: dict[str, bool] = {}

        stack = {
            "warehouse":      c.data_warehouse,
            "orchestration":  c.orchestrator,
            "ingestion":      c.ingestion,
            "transformation": c.transformation,
            "bi":             c.bi_tool,
            "quality":        c.quality or "great-expectations",
            "catalog":        c.catalog or "openmetadata",
            "storage":        c.data_lake or "none",
        }

        # Compatibility checks
        pairs = [
            (c.transformation, c.data_warehouse),
            (c.ingestion, c.data_warehouse),
            (c.orchestrator, c.transformation),
        ]
        for a, b in pairs:
            key = f"{a}↔{b}"
            compat = COMPAT.get((a, b), COMPAT.get((b, a), None))
            if compat is False:
                warnings.append(f"Incompatibilité détectée : {a} et {b} ne sont pas compatibles nativement.")
            compatibility[key] = compat if compat is not None else True

        # Volume-based warnings
        vol_recs = VOLUME_RECOMMENDATIONS.get(c.data_volume, {})
        if c.data_volume == "xlarge" and c.transformation in ("dbt", "dbt Core", "dbt core"):
            warnings.append(
                "Volume xlarge avec dbt seul : envisagez dbt + Spark ou Databricks pour les transformations distribuées."
            )
        if c.data_volume == "small" and c.data_warehouse == "snowflake":
            warnings.append(
                "Snowflake sur volume small est surdimensionné. DuckDB ou PostgreSQL sera plus économique."
            )

        # Mode streaming
        if c.processing_mode == "realtime" and c.transformation not in ("flink", "spark"):
            warnings.append(
                f"Mode temps réel avec {c.transformation} : dbt/SQLMesh ne gèrent que le batch. "
                "Ajoutez Flink ou Spark Streaming pour le temps réel."
            )

        # Budget coherence
        if c.budget == "low" and c.data_warehouse in ("snowflake", "databricks"):
            warnings.append(
                f"{c.data_warehouse} est une solution SaaS payante. "
                "Pour un budget faible, PostgreSQL ou ClickHouse sont open-source et autohébergés."
            )

        # Maturity warnings
        for layer, tool in stack.items():
            mat = MATURITY.get(tool, 3)
            if mat <= 2:
                warnings.append(f"{tool} (couche {layer}) est peu mature — prévoyez du temps de stabilisation.")

        # Build alternatives excluding current choices
        alternatives = {
            layer: [t for t in opts if t != stack.get(layer)]
            for layer, opts in ALTERNATIVES.items()
        }

        output = StackAdvisorOutput(
            validated_stack=stack,
            alternatives=alternatives,
            warnings=warnings,
            compatibility_matrix=compatibility,
        )
        output.artifacts["stack_validation.md"] = self._render(
            request, stack, warnings, compatibility, vol_recs, alternatives
        )
        return output

    def _render(
        self, request: BusinessRequest, stack: dict, warnings: list,
        compat: dict, vol_recs: dict, alternatives: dict
    ) -> str:
        c = request.architecture_constraints
        lines = [
            f"# Stack Validation — {request.business_request}",
            "",
            f"**Volume:** {c.data_volume}  |  **Mode:** {c.processing_mode}  |  **Budget:** {c.budget}",
            "",
            "## Stack validée",
            "",
        ]
        for layer, tool in stack.items():
            mat = MATURITY.get(tool, 3)
            stars = "★" * mat + "☆" * (5 - mat)
            lines.append(f"| {layer:16} | `{tool:25}` | {stars} |")

        if warnings:
            lines += ["", "## ⚠️ Avertissements", ""]
            for w in warnings:
                lines.append(f"- {w}")

        if vol_recs:
            lines += ["", f"## Recommandations pour volume {c.data_volume}", ""]
            for layer, rec in vol_recs.items():
                lines.append(f"- **{layer}**: {rec}")

        lines += ["", "## Compatibilité", ""]
        for pair, ok in compat.items():
            icon = "✅" if ok else "❌"
            lines.append(f"- {icon} {pair}")

        lines += ["", "## Alternatives disponibles", ""]
        for layer, alts in alternatives.items():
            if alts:
                lines.append(f"- **{layer}**: {', '.join(alts[:4])}")

        return "\n".join(lines)
