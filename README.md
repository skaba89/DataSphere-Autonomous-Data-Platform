# DataSphere Autonomous Data Platform

![Tests](https://img.shields.io/badge/tests-435%20passed-22c55e)
![Coverage](https://img.shields.io/badge/coverage-70%25-22c55e)
![Python](https://img.shields.io/badge/python-3.11%2B-6366f1)
![Version](https://img.shields.io/badge/version-1.2.0-22d3ee)

> Stack-agnostic. Cloud-agnostic. You choose the tools.

DataSphere is an open-source autonomous data platform that lets you assemble your ideal data stack from best-of-breed tools across **14 configurable layers** -- without vendor lock-in.

## Why DataSphere?

Most data platforms force you into a single cloud or tool ecosystem. DataSphere inverts this: define your desired stack in a single `stack.yaml`, and the platform adapts to it.

```
Cloud:          Local Docker | AWS | Azure | GCP | Kubernetes | ...
Warehouse:      PostgreSQL | Snowflake | BigQuery | ClickHouse | ...
Orchestration:  Airflow | Dagster | Prefect | Argo | ...
Ingestion:      Airbyte | Meltano | Kafka Connect | Debezium | ...
Transformation: dbt | SQLMesh | Spark | Polars | ...
Storage/Lake:   MinIO | S3 | ADLS | GCS | Iceberg | Delta Lake | ...
BI:             Superset | Metabase | Grafana | Evidence | ...
Quality:        Great Expectations | Soda Core | dbt tests | ...
Catalog:        OpenMetadata | DataHub | Amundsen | ...
AI/LLM:         OpenAI | Anthropic | Mistral | Ollama | vLLM | ...
Vector DB:      Qdrant | Weaviate | pgvector | Chroma | ...
Infra:          Docker Compose | Kubernetes | Helm | Terraform | ...
Monitoring:     Prometheus | Grafana | Loki | OpenTelemetry | ...
Security:       Vault | Keycloak | Authentik | RBAC | ...
```

## Quick Start

```bash
# Docker
docker run -p 8000:8000 ghcr.io/skaba89/datasphere-autonomous-data-platform:latest

# Python SDK
pip install datasphere-platform
```

```python
from datasphere.client import DataSphereClient
client = DataSphereClient("http://localhost:8000")
result = client.generate("Pipeline analytics ventes", cloud_provider="aws", data_warehouse="snowflake")
```

```bash
# Install CLI
pip install datasphere

# Configure interactively
datasphere wizard

# Validate
datasphere validate stack.yaml

# Deploy (local Docker)
docker compose -f infra/docker/docker-compose.base.yml up -d

# Check status
datasphere status stack.yaml
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (checks job store) |
| GET | `/` | List all endpoints |
| GET | `/stacks/supported` | List supported tool categories |
| GET | `/stacks/adapters` | List all registered adapters |
| POST | `/generate` | Start async generation job |
| POST | `/generate/sync` | Synchronous generation (blocking) |
| GET | `/generate/stream` | SSE stream for async job progress |
| POST | `/proposals` | Get architecture proposals |
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{job_id}` | Get job status and result |
| DELETE | `/jobs/{job_id}` | Delete a job |
| GET | `/jobs/{job_id}/download` | Download job artifacts as ZIP |
| POST | `/jobs/purge` | Purge old jobs |
| POST | `/dbt/generate` | Generate dbt project scaffold |
| POST | `/dags/airflow/generate` | Generate Airflow DAGs |
| POST | `/dagster/generate` | Generate Dagster project |
| POST | `/prefect/generate` | Generate Prefect flows |
| POST | `/terraform/generate` | Generate Terraform IaC |

## Example Configurations

| Example | Cloud | Warehouse | Orchestration | Storage | BI |
|---------|-------|-----------|---------------|---------|-----|
| [local_minimal](configs/examples/local_minimal.yaml) | Docker | PostgreSQL | Airflow | MinIO | Superset |
| [aws_production](configs/examples/aws_production.yaml) | AWS | Redshift | Airflow | S3 | Superset |
| [azure_enterprise](configs/examples/azure_enterprise.yaml) | Azure | Synapse | Dagster | ADLS | Power BI |
| [gcp_analytics](configs/examples/gcp_analytics.yaml) | GCP | BigQuery | Prefect | GCS | Superset |
| [on_premise_k8s](configs/examples/on_premise_k8s.yaml) | K8s | PostgreSQL | Argo | MinIO | Metabase |

## Documentation

- [Architecture](docs/architecture.md)
- [Stack Choices Reference](docs/stack-choices.md)
- [Quick Start](docs/quickstart.md)

## Project Structure

```
datasphere/          Python package
  core/              Config loader + adapter registry
  adapters/          One adapter per tool (14 categories)
  cli/               Interactive wizard + CLI commands
configs/examples/    Ready-to-use stack configurations
infra/
  docker/            Docker Compose files (composable)
  terraform/         Terraform modules (AWS/Azure/GCP)
  helm/              Kubernetes Helm chart
docs/                Architecture + reference docs
```

## License

Apache-2.0
