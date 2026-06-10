# DataSphere Architecture

## Overview

DataSphere is a stack-agnostic, cloud-agnostic autonomous data platform. Instead of locking you into one tool, it lets you assemble the exact stack you need across 14 independent layers.

## Architecture Diagram

```
+------------------------------------------------------------------+
|                    DataSphere Platform                           |
+----------+----------+----------+----------+----------+----------+
|  Cloud   |Warehouse |  Ingest  |Transform |  Storage |   BI    |
|  Layer   |  Layer   |  Layer   |  Layer   |  Layer   |  Layer  |
+----------+----------+----------+----------+----------+----------+
| AWS/GCP  |Postgres  | Airbyte  |   dbt    |  MinIO   |Superset |
| Azure    |Snowflake | Meltano  | SQLMesh  |    S3    |Metabase |
| On-prem  |BigQuery  |  NiFi    |  Spark   |   GCS    |Redash   |
| Local    |ClickHse  |  Kafka   |  Polars  |  ADLS    |Evidence |
|    K8s   |  DuckDB  |Debezium  |  Flink   |  Iceberg |Grafana  |
+----------+----------+----------+----------+----------+----------+
|              Orchestration (Airflow / Dagster / Prefect)        |
+-----------------------------------------------------------------+
|         Quality | Catalog | AI/LLM | Vector DB | Security      |
+-----------------------------------------------------------------+
|              Monitoring & Observability                         |
+-----------------------------------------------------------------+
```

## Layers

| # | Layer | Purpose |
|---|-------|---------|
| 1 | Cloud Provider | Deployment target |
| 2 | Data Warehouse | Analytical query engine |
| 3 | Orchestration | Pipeline scheduling |
| 4 | Ingestion | Data movement |
| 5 | Transformation | Data modeling |
| 6 | Storage/Lake | Raw data storage |
| 7 | BI/Analytics | Visualization |
| 8 | Data Quality | Validation & testing |
| 9 | Data Catalog | Discovery & governance |
| 10 | AI/LLM | Intelligent automation |
| 11 | Vector DB | Embedding storage |
| 12 | Infrastructure | Deployment tooling |
| 13 | Monitoring | Observability |
| 14 | Security | Auth & secrets |

## Adapter Pattern

Each tool is implemented as an adapter implementing `BaseAdapter`:

```python
class BaseAdapter(ABC):
    def connect(self) -> Any          # Return live connection
    def validate(self) -> list[str]   # Return errors or []
    def deploy(self) -> str           # Return docker/terraform snippet
    def status(self) -> dict          # Return health info
```

Adapters are auto-registered via `@registry.register(category, name)`.
