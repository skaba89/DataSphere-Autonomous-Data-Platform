# Quick Start

## Prerequisites
- Python 3.11+
- Docker & Docker Compose (for local deployments)

## Installation

```bash
pip install datasphere
```

Or from source:
```bash
git clone https://github.com/skaba89/datasphere-autonomous-data-platform
cd datasphere-autonomous-data-platform
pip install -e ".[postgresql,airflow,dbt,minio,superset,qdrant,prometheus,vault]"
```

## 1. Configure Your Stack

Run the interactive wizard:
```bash
datasphere wizard
```

Or copy an example config:
```bash
cp configs/examples/local_minimal.yaml stack.yaml
```

## 2. Validate Your Config

```bash
datasphere validate stack.yaml
```

## 3. Deploy (Local Docker)

```bash
# Set required environment variables
export POSTGRES_PASSWORD=changeme
export AIRFLOW_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export VAULT_TOKEN=root-token

# Start base services
docker compose -f infra/docker/docker-compose.base.yml up -d

# Start orchestration (Airflow)
docker compose -f infra/docker/docker-compose.base.yml \
               -f infra/docker/docker-compose.orchestration.yml \
               --profile airflow up -d

# Start BI (Superset)
export SUPERSET_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export SUPERSET_PASSWORD=admin
docker compose -f infra/docker/docker-compose.base.yml \
               -f infra/docker/docker-compose.bi.yml \
               --profile superset up -d
```

## 4. Check Status

```bash
datasphere status stack.yaml
```

## 5. Deploy on Kubernetes

```bash
# Add Helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install DataSphere
helm install datasphere ./infra/helm/datasphere \
  -f infra/helm/datasphere/values.yaml \
  --set platform.environment=production \
  --namespace datasphere \
  --create-namespace
```

## Service URLs (local)

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| Airflow | http://localhost:8080 | airflow / airflow |
| Superset | http://localhost:8088 | admin / admin |
| Metabase | http://localhost:3000 | Setup on first run |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Qdrant UI | http://localhost:6333/dashboard | No auth |
| Prometheus | http://localhost:9090 | No auth |
| Grafana | http://localhost:3001 | admin / changeme |
| Vault | http://localhost:8200 | Token from VAULT_TOKEN |
| Keycloak | http://localhost:8081 | admin / changeme |
