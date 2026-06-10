from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


CloudProvider = Literal[
    "aws", "azure", "gcp", "local-docker", "ovhcloud", "scaleway", "on-premise", "kubernetes"
]

DataWarehouse = Literal[
    "snowflake", "bigquery", "redshift", "azure-synapse", "databricks",
    "postgresql", "clickhouse", "duckdb",
]

Orchestrator = Literal["airflow", "dagster", "prefect", "argo", "kestra"]

IngestionTool = Literal["airbyte", "meltano", "nifi", "kafka-connect", "debezium", "fivetran-like"]

TransformationTool = Literal["dbt", "dbt Core", "sqlmesh", "SQLMesh", "spark", "flink", "polars"]

DataLake = Literal["s3", "S3", "adls", "gcs", "minio", "MinIO", "hdfs", "iceberg", "delta-lake", "hudi", "none"]

BiTool = Literal[
    "superset", "Superset", "metabase", "Metabase", "grafana", "powerbi",
    "tableau", "evidence", "redash",
]

CatalogTool = Literal["openmetadata", "OpenMetadata", "datahub", "DataHub", "amundsen", "marquez"]

QualityTool = Literal[
    "great-expectations", "Great Expectations", "soda-core", "Soda Core",
    "dbt-tests", "deequ",
]

DeploymentTarget = Literal[
    "docker-compose", "Docker Compose", "kubernetes", "Kubernetes",
    "helm", "terraform", "Terraform", "managed",
]

SecurityControl = Literal[
    "RBAC", "rbac", "RLS", "rls", "Vault", "vault",
    "Keycloak", "keycloak", "Authentik", "authentik",
    "JWT", "jwt", "OIDC", "oidc", "secret-manager",
]

Budget = Literal["low", "medium", "enterprise"]
DataVolume = Literal["small", "medium", "large", "xlarge"]
ProcessingMode = Literal["batch", "realtime", "both"]


class ArchitectureConstraints(BaseModel):
    cloud_provider: str = Field(..., description="Cloud ou infrastructure cible")
    data_warehouse: str = Field(..., description="Data warehouse cible")
    orchestrator: str = Field(..., description="Orchestrateur de pipelines")
    ingestion: str = Field(..., description="Outil d'ingestion")
    transformation: str = Field(..., description="Outil de transformation")
    data_lake: Optional[str] = Field(None, description="Stockage data lake")
    bi_tool: str = Field(..., description="Outil BI")
    catalog: Optional[str] = Field(None, description="Catalogue de données")
    quality: Optional[str] = Field(None, description="Outil de qualité des données")
    deployment: str = Field(..., description="Mode de déploiement")
    iac: Optional[str] = Field(None, description="Infrastructure as Code")
    security: list[str] = Field(default_factory=list, description="Contrôles de sécurité")
    budget: Budget = Field(default="medium", description="Budget disponible")
    data_volume: DataVolume = Field(default="medium", description="Volume de données")
    processing_mode: ProcessingMode = Field(default="batch", description="Mode de traitement")
    region: Optional[str] = Field(None, description="Région cloud")
    existing_infra: Optional[str] = Field(None, description="Infrastructure existante")

    def normalize(self) -> "ArchitectureConstraints":
        """Normalize tool names to lowercase canonical form."""
        mapping = {
            "dbt Core": "dbt", "dbt core": "dbt",
            "SQLMesh": "sqlmesh",
            "Docker Compose": "docker-compose",
            "Kubernetes": "kubernetes",
            "Terraform": "terraform",
            "OpenMetadata": "openmetadata",
            "DataHub": "datahub",
            "Great Expectations": "great-expectations",
            "Soda Core": "soda-core",
            "MinIO": "minio",
            "Superset": "superset",
            "Metabase": "metabase",
            "Local Docker": "local-docker",
            "local docker": "local-docker",
        }
        data = self.model_dump()
        for field in ("data_warehouse", "orchestrator", "ingestion", "transformation",
                      "data_lake", "bi_tool", "catalog", "quality", "deployment",
                      "iac", "cloud_provider"):
            if data.get(field) in mapping:
                data[field] = mapping[data[field]]
        return ArchitectureConstraints(**data)


class BusinessRequest(BaseModel):
    business_request: str = Field(..., description="Besoin métier en langage naturel")
    architecture_constraints: ArchitectureConstraints = Field(
        ..., description="Contraintes et choix techniques"
    )

    def normalized(self) -> "BusinessRequest":
        return BusinessRequest(
            business_request=self.business_request,
            architecture_constraints=self.architecture_constraints.normalize(),
        )
