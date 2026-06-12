"""
Predefined stack templates for common data platform use cases.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class StackTemplate:
    id: str
    name: str
    description: str
    category: str          # "startup", "enterprise", "analytics", "streaming", "ml"
    complexity: str        # "low", "medium", "high"
    estimated_monthly_usd: int
    time_to_deploy: str    # "1 day", "1 week", "1 month"
    constraints: dict      # ArchitectureConstraints-compatible dict
    tags: list[str] = field(default_factory=list)
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)


_TEMPLATES: list[StackTemplate] = [
    StackTemplate(
        id="startup-analytics",
        name="Startup Analytics",
        description="Lightweight open-source stack for early-stage startups with minimal budget.",
        category="startup",
        complexity="low",
        estimated_monthly_usd=200,
        time_to_deploy="1 day",
        constraints={
            "cloud": "aws",
            "warehouse": "postgresql",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
            "budget": "low",
        },
        tags=["open-source", "low-cost", "self-hosted", "startup"],
        pros=["Fully open-source", "Low cost", "Easy to self-host"],
        cons=["No managed services", "Requires DevOps knowledge"],
        use_cases=["SaaS metrics", "Sales analytics", "Product analytics"],
    ),
    StackTemplate(
        id="modern-data-stack-aws",
        name="Modern Data Stack AWS",
        description="Industry-standard modern data stack on AWS with best-in-class managed services.",
        category="analytics",
        complexity="medium",
        estimated_monthly_usd=2500,
        time_to_deploy="1 week",
        constraints={
            "cloud": "aws",
            "warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "fivetran",
            "transformation": "dbt",
            "bi_tool": "tableau",
            "deployment": "kubernetes",
            "budget": "medium",
        },
        tags=["aws", "snowflake", "managed", "enterprise-ready"],
        pros=["Fully managed services", "Scalable", "Strong ecosystem"],
        cons=["Higher cost", "Vendor lock-in risk"],
        use_cases=["Enterprise BI", "Data democratization", "Self-service analytics"],
    ),
    StackTemplate(
        id="gcp-data-platform",
        name="GCP Data Platform",
        description="Native GCP data platform leveraging BigQuery and Looker for analytics at scale.",
        category="analytics",
        complexity="medium",
        estimated_monthly_usd=1800,
        time_to_deploy="1 week",
        constraints={
            "cloud": "gcp",
            "warehouse": "bigquery",
            "orchestrator": "dagster",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "looker",
            "deployment": "kubernetes",
            "budget": "medium",
        },
        tags=["gcp", "bigquery", "looker", "google-cloud"],
        pros=["Native GCP integration", "Serverless BigQuery", "Excellent ML integration"],
        cons=["GCP dependency", "Looker licensing cost"],
        use_cases=["Analytics at scale", "Real-time reporting", "ML-ready platform"],
    ),
    StackTemplate(
        id="azure-enterprise",
        name="Azure Enterprise",
        description="Enterprise-grade Azure data platform with Synapse and Tableau for large organizations.",
        category="enterprise",
        complexity="high",
        estimated_monthly_usd=5000,
        time_to_deploy="1 month",
        constraints={
            "cloud": "azure",
            "warehouse": "synapse",
            "orchestrator": "airflow",
            "ingestion": "fivetran",
            "transformation": "dbt",
            "bi_tool": "tableau",
            "deployment": "kubernetes",
            "budget": "enterprise",
        },
        tags=["azure", "synapse", "enterprise", "microsoft"],
        pros=["Microsoft ecosystem integration", "Enterprise security", "Synapse unified analytics"],
        cons=["Complex setup", "High cost", "Azure expertise required"],
        use_cases=["Enterprise data warehouse", "Cross-org reporting", "Azure AD integration"],
    ),
    StackTemplate(
        id="open-source-stack",
        name="Open Source Stack",
        description="100% open-source stack with zero licensing cost, runs on any infrastructure.",
        category="startup",
        complexity="medium",
        estimated_monthly_usd=100,
        time_to_deploy="1 week",
        constraints={
            "cloud": "other",
            "warehouse": "duckdb",
            "orchestrator": "prefect",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "docker-compose",
            "budget": "low",
        },
        tags=["open-source", "no-vendor-lock", "portable", "budget"],
        pros=["Zero licensing cost", "Full data ownership", "Runs on any cloud"],
        cons=["No managed services", "Higher operational burden"],
        use_cases=["Budget-conscious analytics", "Open-source advocates", "Multi-cloud portability"],
    ),
    StackTemplate(
        id="realtime-analytics",
        name="Real-time Analytics",
        description="Streaming-first architecture for real-time dashboards and event-driven analytics.",
        category="streaming",
        complexity="high",
        estimated_monthly_usd=3000,
        time_to_deploy="1 month",
        constraints={
            "cloud": "aws",
            "warehouse": "clickhouse",
            "orchestrator": "dagster",
            "ingestion": "kafka-connect",
            "transformation": "dbt",
            "bi_tool": "grafana",
            "deployment": "kubernetes",
            "budget": "medium",
        },
        tags=["streaming", "kafka", "clickhouse", "real-time", "low-latency"],
        pros=["Sub-second query latency", "Handles high-throughput events", "Kafka ecosystem"],
        cons=["Complex operational model", "Kafka expertise required"],
        use_cases=["Real-time dashboards", "Event-driven analytics", "IoT data"],
    ),
    StackTemplate(
        id="ml-platform",
        name="ML Platform",
        description="End-to-end machine learning platform with feature engineering and model pipelines.",
        category="ml",
        complexity="high",
        estimated_monthly_usd=4000,
        time_to_deploy="1 month",
        constraints={
            "cloud": "aws",
            "warehouse": "snowflake",
            "orchestrator": "dagster",
            "ingestion": "airbyte",
            "transformation": "spark",
            "bi_tool": "superset",
            "deployment": "kubernetes",
            "budget": "enterprise",
        },
        tags=["ml", "feature-engineering", "spark", "ai", "data-science"],
        pros=["ML-optimized pipeline", "Spark for large-scale transforms", "Dagster asset-based model"],
        cons=["High complexity", "Spark cluster management overhead"],
        use_cases=["Feature engineering", "Model training pipelines", "A/B testing"],
    ),
    StackTemplate(
        id="fintech-compliance",
        name="Fintech Compliance",
        description="Secure, compliant data platform for financial services with SOC2 and PCI-DSS support.",
        category="enterprise",
        complexity="high",
        estimated_monthly_usd=6000,
        time_to_deploy="1 month",
        constraints={
            "cloud": "aws",
            "warehouse": "redshift",
            "orchestrator": "airflow",
            "ingestion": "fivetran",
            "transformation": "dbt",
            "bi_tool": "tableau",
            "deployment": "kubernetes",
            "budget": "enterprise",
            "security": ["RBAC", "SOC2", "PCI-DSS"],
        },
        tags=["fintech", "compliance", "security", "pci-dss", "soc2", "redshift"],
        pros=["SOC2 and PCI-DSS ready", "Redshift row-level security", "Audit logging"],
        cons=["Very high cost", "Complex compliance overhead"],
        use_cases=["Transaction analytics", "Risk management", "Regulatory reporting"],
    ),
    StackTemplate(
        id="ecommerce-analytics",
        name="E-commerce Analytics",
        description="GCP-native analytics platform optimized for e-commerce data volumes and use cases.",
        category="analytics",
        complexity="medium",
        estimated_monthly_usd=1200,
        time_to_deploy="1 week",
        constraints={
            "cloud": "gcp",
            "warehouse": "bigquery",
            "orchestrator": "prefect",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "kubernetes",
            "budget": "medium",
        },
        tags=["ecommerce", "gcp", "bigquery", "metabase", "customer-analytics"],
        pros=["Cost-effective BigQuery", "Metabase self-service BI", "Prefect simplicity"],
        cons=["GCP-only", "Metabase limitations at scale"],
        use_cases=["Sales reporting", "Customer segmentation", "Inventory analytics"],
    ),
    StackTemplate(
        id="local-dev",
        name="Local Dev Stack",
        description="Zero-cost local development environment for learning, prototyping, and POC.",
        category="startup",
        complexity="low",
        estimated_monthly_usd=0,
        time_to_deploy="1 day",
        constraints={
            "cloud": "other",
            "warehouse": "duckdb",
            "orchestrator": "prefect",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "docker-compose",
            "budget": "low",
        },
        tags=["local", "free", "development", "poc", "learning", "duckdb"],
        pros=["Completely free", "Runs on laptop", "Fast iteration"],
        cons=["Not production-ready", "Limited scalability"],
        use_cases=["Local development", "Proof of concept", "Learning"],
    ),
]


class TemplateRegistry:
    def __init__(self):
        self._templates: dict[str, StackTemplate] = {}
        for t in _TEMPLATES:
            self._templates[t.id] = t

    def list_all(self) -> list[StackTemplate]:
        return list(self._templates.values())

    def get(self, template_id: str) -> StackTemplate | None:
        return self._templates.get(template_id)

    def list_by_category(self, category: str) -> list[StackTemplate]:
        return [t for t in self._templates.values() if t.category == category]

    def search(self, query: str) -> list[StackTemplate]:
        q = query.lower()
        results = []
        for t in self._templates.values():
            if (
                q in t.name.lower()
                or q in t.description.lower()
                or any(q in tag.lower() for tag in t.tags)
                or q in t.category.lower()
            ):
                results.append(t)
        return results


template_registry = TemplateRegistry()
