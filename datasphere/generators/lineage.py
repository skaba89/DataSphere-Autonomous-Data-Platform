"""Génère un diagramme de lineage Mermaid depuis une stack validée."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Display label maps
# ---------------------------------------------------------------------------

_INGESTION_LABELS = {
    "airbyte": "Airbyte",
    "meltano": "Meltano",
    "fivetran": "Fivetran",
    "kafka-connect": "Kafka Connect",
    "debezium": "Debezium",
    "nifi": "Apache NiFi",
}

_TRANSFORM_LABELS = {
    "dbt": "dbt Core",
    "spark": "Apache Spark",
    "sqlmesh": "SQLMesh",
    "flink": "Apache Flink",
    "polars": "Polars",
}

_WAREHOUSE_LABELS = {
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "redshift": "Redshift",
    "postgresql": "PostgreSQL",
    "clickhouse": "ClickHouse",
    "duckdb": "DuckDB",
    "databricks": "Databricks",
    "synapse": "Azure Synapse",
}

_ORCHESTRATOR_LABELS = {
    "airflow": "Apache Airflow",
    "dagster": "Dagster",
    "prefect": "Prefect",
    "argo": "Argo Workflows",
    "kestra": "Kestra",
}

_BI_LABELS = {
    "metabase": "Metabase",
    "superset": "Apache Superset",
    "tableau": "Tableau",
    "looker": "Looker",
    "redash": "Redash",
    "powerbi": "Power BI",
    "evidence": "Evidence",
}

_QUALITY_LABELS = {
    "great-expectations": "Great Expectations",
    "soda-core": "Soda Core",
    "dbt-tests": "dbt Tests",
    "deequ": "Amazon Deequ",
}

_CATALOG_LABELS = {
    "datahub": "DataHub",
    "amundsen": "Amundsen",
    "openmetadata": "OpenMetadata",
    "marquez": "Marquez",
}


def _label(mapping: dict, key: str | None, default: str = "") -> str:
    if not key:
        return default
    return mapping.get(key.lower(), key)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class LineageOutput:
    mermaid: str
    nodes: list[str]
    edges: list[tuple]
    format: str = "mermaid"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class LineageGenerator:
    """Génère un diagramme Mermaid flowchart LR depuis une stack validée."""

    def generate(self, stack: dict, business_request: str = "") -> LineageOutput:
        """
        Generate a data lineage diagram from a validated stack dict.

        stack keys: cloud_provider, data_warehouse, orchestrator, ingestion,
                    transformation, bi_tool, deployment, data_lake, catalog,
                    quality, ...
        """
        # Resolve labels
        ingestion_label = _label(_INGESTION_LABELS, stack.get("ingestion"), "Ingestion Tool")
        transform_label = _label(_TRANSFORM_LABELS, stack.get("transformation"), "Transformation")
        warehouse_label = _label(_WAREHOUSE_LABELS, stack.get("data_warehouse"), "Data Warehouse")
        orch_label = _label(_ORCHESTRATOR_LABELS, stack.get("orchestrator"), "Orchestrator")
        bi_label = _label(_BI_LABELS, stack.get("bi_tool"), "BI Tool")
        quality_label = _label(_QUALITY_LABELS, stack.get("quality"), "") if stack.get("quality") else ""
        catalog_label = _label(_CATALOG_LABELS, stack.get("catalog"), "") if stack.get("catalog") else ""
        cloud = stack.get("cloud_provider", "Cloud")

        has_quality = bool(quality_label)
        has_catalog = bool(catalog_label)

        # Build nodes list (display names)
        nodes: list[str] = [
            "Source Systems",
            ingestion_label,
            f"{warehouse_label} Raw Layer",
            transform_label,
        ]
        if has_quality:
            nodes.append(quality_label)
        nodes.append(f"{warehouse_label} Serving Layer")
        nodes.append(bi_label)
        nodes.append(orch_label)
        if has_catalog:
            nodes.append(catalog_label)

        # Build edges (source, target, label)
        edges: list[tuple] = [
            ("src", "ingest", "extract"),
            ("ingest", "raw", "load"),
            ("raw", "transform", "read"),
        ]
        if has_quality:
            edges.append(("transform", "quality", "validate"))
            edges.append(("quality", "serving", "write"))
        else:
            edges.append(("transform", "serving", "write"))
        edges.append(("serving", "bi", "query"))
        edges.append(("orch", "ingest", "schedules"))
        edges.append(("orch", "transform", "schedules"))
        if has_quality:
            edges.append(("orch", "quality", "schedules"))
        if has_catalog:
            edges.append(("catalog", "raw", "indexes"))
            edges.append(("catalog", "serving", "indexes"))

        # Build Mermaid string
        lines: list[str] = ["flowchart LR"]

        # Style classes
        lines += [
            "    classDef source fill:#1a1d27,stroke:#6366f1,color:#e2e8f0",
            "    classDef ingestion fill:#1a1d27,stroke:#22d3ee,color:#e2e8f0",
            "    classDef storage fill:#1a1d27,stroke:#f59e0b,color:#e2e8f0",
            "    classDef transform fill:#1a1d27,stroke:#22c55e,color:#e2e8f0",
            "    classDef quality fill:#1a1d27,stroke:#f97316,color:#e2e8f0",
            "    classDef serving fill:#1a1d27,stroke:#a78bfa,color:#e2e8f0",
            "    classDef orchestration fill:#1a1d27,stroke:#ef4444,color:#e2e8f0",
            "    classDef catalog fill:#1a1d27,stroke:#ec4899,color:#e2e8f0",
            "",
        ]

        # Node definitions — source outside the platform subgraph
        lines.append('    src["📦 Source Systems"]:::source')
        lines.append("")

        # Platform subgraph
        cloud_display = cloud.upper() if len(cloud) <= 3 else cloud.capitalize()
        lines.append(f'    subgraph Platform ["☁ {cloud_display} Platform"]')
        lines.append(f'        ingest["{ingestion_label}"]:::ingestion')
        lines.append(f'        raw["{warehouse_label}\\nRaw Layer"]:::storage')
        lines.append(f'        transform["{transform_label}"]:::transform')
        if has_quality:
            lines.append(f'        quality["{quality_label}"]:::quality')
        lines.append(f'        serving["{warehouse_label}\\nServing Layer"]:::serving')
        lines.append("    end")
        lines.append("")

        # BI node (outside platform)
        lines.append(f'    bi["{bi_label}"]:::serving')
        lines.append("")

        # Orchestrator node
        lines.append(f'    orch["{orch_label}"]:::orchestration')

        # Catalog node
        if has_catalog:
            lines.append(f'    catalog["{catalog_label}"]:::catalog')
        lines.append("")

        # Edges
        lines.append('    src --"extract"--> ingest')
        lines.append('    ingest --"load"--> raw')
        lines.append('    raw --"read"--> transform')
        if has_quality:
            lines.append('    transform --"validate"--> quality')
            lines.append('    quality --"write"--> serving')
        else:
            lines.append('    transform --"write"--> serving')
        lines.append('    serving --"query"--> bi')
        lines.append('    orch -.->|"schedules"| ingest')
        lines.append('    orch -.->|"schedules"| transform')
        if has_quality:
            lines.append('    orch -.->|"schedules"| quality')
        if has_catalog:
            lines.append('    catalog -.->|"indexes"| raw')
            lines.append('    catalog -.->|"indexes"| serving')

        mermaid = "\n".join(lines)
        return LineageOutput(mermaid=mermaid, nodes=nodes, edges=edges)

    @staticmethod
    def embed_url(mermaid: str) -> str:
        """Generate a mermaid.live embed URL from a mermaid diagram string."""
        payload = json.dumps({"code": mermaid, "mermaid": {"theme": "dark"}})
        encoded = base64.b64encode(payload.encode()).decode()
        return f"https://mermaid.live/edit#base64:{encoded}"
