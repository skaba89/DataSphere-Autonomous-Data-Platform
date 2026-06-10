from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


ALLOWED = {
    "cloud": ["local-docker","aws","azure","gcp","ovhcloud","scaleway","on-premise","kubernetes"],
    "warehouse": ["postgresql","snowflake","bigquery","redshift","azure-synapse","databricks","clickhouse","duckdb"],
    "orchestration": ["airflow","dagster","prefect","kestra","argo"],
    "ingestion": ["airbyte","meltano","nifi","kafka-connect","debezium","fivetran-like"],
    "transformation": ["dbt","sqlmesh","spark","flink","polars"],
    "storage": ["minio","s3","adls","gcs","hdfs","iceberg","delta-lake","hudi"],
    "bi": ["superset","metabase","redash","evidence","grafana","powerbi","tableau"],
    "quality": ["great-expectations","soda-core","dbt-tests","deequ"],
    "catalog": ["openmetadata","datahub","amundsen","marquez"],
    "ai": ["openai","azure-openai","anthropic","mistral","ollama","vllm","lm-studio"],
    "vector": ["qdrant","weaviate","milvus","pgvector","chroma"],
    "infrastructure": ["docker-compose","kubernetes","helm","terraform","ansible","github-actions","gitlab-ci"],
    "monitoring": ["prometheus","grafana","loki","opentelemetry","elk"],
    "security": ["vault","keycloak","authentik","oidc","jwt","rbac","secret-manager"],
}


@dataclass
class StackConfig:
    name: str = "my-datasphere"
    environment: str = "development"
    version: str = "1.0.0"
    cloud: dict[str, Any] = field(default_factory=lambda: {"provider": "local-docker"})
    warehouse: dict[str, Any] = field(default_factory=lambda: {"type": "postgresql"})
    orchestration: dict[str, Any] = field(default_factory=lambda: {"type": "airflow"})
    ingestion: dict[str, Any] = field(default_factory=lambda: {"type": "airbyte"})
    transformation: dict[str, Any] = field(default_factory=lambda: {"type": "dbt"})
    storage: dict[str, Any] = field(default_factory=lambda: {"type": "minio"})
    bi: dict[str, Any] = field(default_factory=lambda: {"type": "superset"})
    quality: dict[str, Any] = field(default_factory=lambda: {"type": "great-expectations"})
    catalog: dict[str, Any] = field(default_factory=lambda: {"type": "openmetadata"})
    ai: dict[str, Any] = field(default_factory=lambda: {"type": "openai"})
    vector: dict[str, Any] = field(default_factory=lambda: {"type": "qdrant"})
    infrastructure: dict[str, Any] = field(default_factory=lambda: {"type": "docker-compose"})
    monitoring: dict[str, Any] = field(default_factory=lambda: {"type": "prometheus"})
    security: dict[str, Any] = field(default_factory=lambda: {"type": "vault"})

    @classmethod
    def from_file(cls, path: str | Path) -> "StackConfig":
        data = yaml.safe_load(Path(path).read_text())
        platform = data.pop("platform", {})
        return cls(
            name=platform.get("name", "my-datasphere"),
            environment=platform.get("environment", "development"),
            version=platform.get("version", "1.0.0"),
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )

    def validate(self) -> list[str]:
        errors = []
        for category, allowed in ALLOWED.items():
            cfg = getattr(self, category, {})
            tool = cfg.get("type") or cfg.get("provider")
            if tool and tool not in allowed:
                errors.append(f"{category}: '{tool}' not in {allowed}")
        return errors

    def to_yaml(self) -> str:
        data = {
            "platform": {"name": self.name, "environment": self.environment, "version": self.version},
            **{k: getattr(self, k) for k in ALLOWED},
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
