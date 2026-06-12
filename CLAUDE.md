# DataSphere — CLAUDE.md

## Project Overview
DataSphere Autonomous Data Platform — génère automatiquement des architectures data complètes à partir d'une description métier.

## Architecture
- `datasphere/agents/` — 6 agents IA (stack_advisor, cloud_architect, infrastructure, cost_optimization, security_compliance, deployment)
- `datasphere/generators/` — générateurs de code (dbt, airflow, dagster, prefect, terraform, lineage, templates, stack_diff)
- `datasphere/api/` — FastAPI REST API avec auth, rate limiting, SSE streaming, webhooks, métriques
- `datasphere/client.py` — SDK Python client
- `datasphere/cli/` — CLI interactive
- `datasphere/plugins.py` — système de plugins
- `infra/helm/` — Helm chart Kubernetes v1.2.0
- `tests/` — 667+ tests pytest

## Key Commands
```bash
# Run tests
python -m pytest tests/ -q

# Run with coverage
python -m pytest tests/ --cov=datasphere --cov-report=term-missing

# Start API server
uvicorn datasphere.api.app:app --reload --port 8000

# CLI
python -m datasphere.cli.main generate "Pipeline analytics" --cloud aws --warehouse snowflake

# Bump version
python scripts/bump_version.py patch

# Docker
docker build -t datasphere:dev .
docker run -p 8000:8000 datasphere:dev
```

## Environment Variables
- `DATASPHERE_API_KEY` — enable Bearer auth
- `DATASPHERE_REDIS_URL` — use Redis job store
- `DATASPHERE_JOB_DB` — SQLite path (default: ~/.datasphere/jobs.db)
- `DATASPHERE_ARTIFACT_DIR` — artifact storage path
- `DATASPHERE_OTLP_ENDPOINT` — OpenTelemetry OTLP endpoint
- `DATASPHERE_SLACK_WEBHOOK_URL` — Slack notifications
- `DATASPHERE_TEAMS_WEBHOOK_URL` — Teams notifications
- `DATASPHERE_RATE_LIMIT_RPM` — rate limit (default: 60)
- `DATASPHERE_CORS_ORIGINS` — CORS origins (default: localhost)

## API Endpoints (37 total)

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/health` | Liveness probe (alias) |
| GET | `/readyz` | Readiness probe (checks job store) |
| GET | `/` | List all endpoints |
| GET | `/metrics` | Prometheus metrics |
| GET | `/plugins` | List registered plugins |

### Generation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Start async generation job |
| POST | `/generate/sync` | Synchronous generation (blocking) |
| GET | `/generate/stream` | SSE stream for async job progress |
| POST | `/generate/from-template` | Generate from a named template |

### Jobs
| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{job_id}` | Get job status and result |
| DELETE | `/jobs/{job_id}` | Delete a job |
| GET | `/jobs/{job_id}/download` | Download job artifacts as ZIP |
| POST | `/jobs/purge` | Purge old jobs |

### Artifacts
| Method | Path | Description |
|--------|------|-------------|
| GET | `/artifacts/{job_id}` | List artifacts for a job |
| GET | `/artifacts/{job_id}/download` | Download artifacts as ZIP |
| GET | `/artifacts/{job_id}/{filename}` | Download a single artifact file |

### Recommendations
| Method | Path | Description |
|--------|------|-------------|
| POST | `/proposals` | Get architecture proposals |

### Generators
| Method | Path | Description |
|--------|------|-------------|
| POST | `/dbt/generate` | Generate dbt project scaffold |
| POST | `/dags/airflow/generate` | Generate Airflow DAGs |
| POST | `/dagster/generate` | Generate Dagster project |
| POST | `/prefect/generate` | Generate Prefect flows |
| POST | `/terraform/generate` | Generate Terraform IaC |
| POST | `/lineage/generate` | Generate data lineage graph |

### Analysis
| Method | Path | Description |
|--------|------|-------------|
| POST | `/costs/estimate` | Estimate infrastructure costs |
| POST | `/costs/optimize` | AI-powered RI / Savings Plans recommendations |
| POST | `/stacks/diff` | Diff two stack configurations |

### Templates
| Method | Path | Description |
|--------|------|-------------|
| GET | `/templates` | List available templates |
| GET | `/templates/{template_id}` | Get a specific template |

### Catalog
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stacks/supported` | List supported tool categories |
| GET | `/stacks/adapters` | List all registered adapters |

### Webhooks
| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks` | Register a webhook |
| GET | `/webhooks` | List webhooks |
| GET | `/webhooks/deliveries` | List webhook delivery history |
| DELETE | `/webhooks/{webhook_id}` | Delete a webhook |

### UI
| Method | Path | Description |
|--------|------|-------------|
| GET | `/ui` | Serve the web UI (HTML) |

## Testing Guidelines
- All tests in `tests/` — use pytest fixtures from `conftest.py`
- `client` fixture = FastAPI TestClient (auth disabled)
- `auth_client` fixture = TestClient with Bearer auth
- Docker integration tests skip if `DATASPHERE_BASE_URL` not set
- Run `python -m pytest tests/ -q` before every commit

## Current Version: 1.2.0
Branch: claude/beautiful-hopper-4x7be3
