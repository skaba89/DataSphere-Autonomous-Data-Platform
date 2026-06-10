from __future__ import annotations
from datasphere.agents.base_agent import BaseAgent
from datasphere.models.request import BusinessRequest, ArchitectureConstraints
from datasphere.models.output import AgentOutput, DeploymentOutput

CICD_PLATFORMS: dict[str, str] = {
    "aws":          "GitHub Actions + AWS CodePipeline",
    "azure":        "GitHub Actions + Azure DevOps",
    "gcp":          "GitHub Actions + Cloud Build",
    "local-docker": "GitHub Actions",
    "kubernetes":   "GitHub Actions + ArgoCD",
    "on-premise":   "GitLab CI/CD",
}

ROLLBACK_STRATEGIES: dict[str, str] = {
    "kubernetes": (
        "ArgoCD sync history — rollback via `argocd app rollback`. "
        "Helm: `helm rollback datasphere <revision>`. "
        "dbt: `dbt run --select state:modified+` avec state précédent."
    ),
    "docker-compose": (
        "Images Docker taguées par commit SHA. "
        "Rollback: `docker compose pull && docker compose up -d` avec la version précédente. "
        "dbt: réexécuter la version précédente du modèle."
    ),
    "terraform": (
        "Terraform state versionné dans S3/GCS/Azure Blob. "
        "Rollback: `terraform apply` avec le plan précédent. "
        "Snapshots RDS/Synapse avant chaque migration."
    ),
}

HEALTH_CHECKS: dict[str, list[str]] = {
    "airflow":       ["GET /api/v1/health → {status: healthy}", "Scheduler heartbeat < 30s"],
    "dagster":       ["GET /dagit/health", "Repository loaded"],
    "prefect":       ["GET /api/health", "Work pools active"],
    "superset":      ["GET /health → OK", "Database connection"],
    "metabase":      ["GET /api/health → {status: ok}", "Database sync complete"],
    "postgresql":    ["pg_isready -U datasphere", "SELECT 1"],
    "clickhouse":    ["SELECT 1 → OK", "HTTP port 8123 accessible"],
    "minio":         ["GET /minio/health/live → 200", "Bucket list accessible"],
    "qdrant":        ["GET /collections → 200", "gRPC port 6334 accessible"],
    "vault":         ["GET /v1/sys/health → {initialized: true}", "Unsealed"],
    "prometheus":    ["GET /-/healthy → OK", "Targets up"],
}


class DeploymentAgent(BaseAgent):
    name = "deployment"
    description = "Génère le pipeline CI/CD, la stratégie de rollback et la configuration monitoring."

    def _run(self, request: BusinessRequest, context: dict) -> DeploymentOutput:
        c = self._constraints(request)
        depl = c.deployment.lower().replace(" ", "-")

        cicd = CICD_PLATFORMS.get(c.cloud_provider, "GitHub Actions")
        rollback = ROLLBACK_STRATEGIES.get(
            "kubernetes" if "kubernetes" in depl or "helm" in depl
            else "terraform" if "terraform" in depl
            else "docker-compose",
            ROLLBACK_STRATEGIES["docker-compose"]
        )

        stages = self._pipeline_stages(c, depl)
        health = self._collect_health_checks(c)
        monitoring = self._monitoring_config(c)

        output = DeploymentOutput(
            cicd_platform=cicd,
            pipeline_stages=stages,
            rollback_strategy=rollback,
            monitoring_config=monitoring,
            health_checks=health,
        )
        output.artifacts[".github/workflows/deploy.yml"] = self._github_actions(c, stages)
        output.artifacts["deployment_report.md"] = self._render_report(
            request, cicd, stages, rollback, health, monitoring
        )
        return output

    def _pipeline_stages(self, c: ArchitectureConstraints, depl: str) -> list[str]:
        stages = [
            "1. lint — Linting Python, SQL (sqlfluff), YAML",
            "2. test-unit — Tests unitaires dbt / Python",
            "3. build — Construction images Docker (tag: commit SHA)",
            "4. push — Push vers registry (ECR/ACR/GCR/Docker Hub)",
            "5. quality-gate — Great Expectations / Soda Core",
        ]
        if "terraform" in depl or (c.iac and "terraform" in c.iac.lower()):
            stages.append("6. terraform-plan — Plan Terraform (commenté sur PR)")
            stages.append("7. terraform-apply — Apply sur merge main (env: production)")
        if "kubernetes" in depl or "helm" in depl:
            stages.append("6. helm-diff — Preview des changements Helm")
            stages.append("7. helm-upgrade — Déploiement Kubernetes")
        else:
            stages.append("6. deploy — docker compose pull && up -d")
        stages += [
            f"{len(stages) + 1}. smoke-test — Tests de smoke post-déploiement",
            f"{len(stages) + 2}. dbt-run — Exécution des modèles dbt",
            f"{len(stages) + 3}. dbt-test — Tests de qualité dbt",
            f"{len(stages) + 4}. notify — Notification Slack / Teams",
        ]
        return stages

    def _collect_health_checks(self, c: ArchitectureConstraints) -> list[str]:
        checks = []
        for tool in (c.orchestrator, c.bi_tool, c.data_warehouse, c.data_lake or ""):
            t = tool.lower().replace(" ", "-")
            if t in HEALTH_CHECKS:
                checks.extend([f"[{tool}] {chk}" for chk in HEALTH_CHECKS[t]])
        return checks

    def _monitoring_config(self, c: ArchitectureConstraints) -> dict:
        return {
            "metrics_retention": "15d" if c.budget == "low" else "90d",
            "alerting": {
                "pipeline_failure":    "alert immédiat → Slack + email",
                "data_quality_breach": "alert immédiat → data owner",
                "warehouse_latency":   "alert si p99 > 30s",
                "disk_usage":          "alert si > 80%",
                "cost_threshold":      f"alert si coût dépasse budget {c.budget}",
            },
            "dashboards": [
                "Pipeline health (Airflow/Dagster/Prefect)",
                "Data freshness par modèle dbt",
                "Query performance warehouse",
                "Data quality scores",
                "Infrastructure resources",
                "Cost tracking",
            ],
        }

    def _github_actions(self, c: ArchitectureConstraints, stages: list[str]) -> str:
        depl = c.deployment.lower().replace(" ", "-")
        deploy_step = ""
        if "kubernetes" in depl or "helm" in depl:
            deploy_step = """      - name: Deploy Helm
        run: |
          helm upgrade --install datasphere ./infra/helm/datasphere \\
            -f infra/helm/datasphere/values.yaml \\
            -f infra/helm/datasphere/values.{cloud}.yaml \\
            --namespace datasphere --create-namespace \\
            --atomic --timeout 10m \\
            --set global.tag=${{ github.sha }}""".format(cloud=c.cloud_provider)
        elif "terraform" in depl:
            deploy_step = """      - name: Terraform Apply
        run: |
          cd infra/terraform
          terraform init
          terraform apply -auto-approve -var="environment=production" """
        else:
            deploy_step = """      - name: Deploy Docker Compose
        run: |
          docker compose pull
          docker compose up -d --remove-orphans"""

        return f"""name: DataSphere Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{{{ github.repository }}}}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{python-version: '3.11'}}
      - run: pip install sqlfluff dbt-core ruff
      - run: ruff check datasphere/
      - run: sqlfluff lint dbt/models/ --dialect {c.data_warehouse.replace('-', '_').replace('azure_synapse', 'tsql')}

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{python-version: '3.11'}}
      - run: pip install -e ".[test]"
      - run: pytest tests/ -v --tb=short

  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{{{ env.REGISTRY }}}}
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ github.sha }}}},${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4
{deploy_step}

      - name: Run dbt
        run: |
          pip install dbt-{c.data_warehouse.replace('-', '_').replace('azure_synapse', 'sqlserver')} || pip install dbt-postgres
          dbt run --profiles-dir dbt --project-dir dbt
          dbt test --profiles-dir dbt --project-dir dbt

      - name: Notify
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {{
              "text": "Deploy ${{{{ job.status }}}}: ${{{{ github.repository }}}} @ ${{{{ github.sha }}}}"
            }}
        env:
          SLACK_WEBHOOK_URL: ${{{{ secrets.SLACK_WEBHOOK_URL }}}}
"""

    def _render_report(
        self, request: BusinessRequest, cicd: str, stages: list[str],
        rollback: str, health: list[str], monitoring: dict
    ) -> str:
        c = request.architecture_constraints
        lines = [
            f"# Deployment Report — {request.business_request}",
            "",
            f"**Cloud:** {c.cloud_provider}  |  **Déploiement:** {c.deployment}  "
            f"|  **CI/CD:** {cicd}",
            "",
            "## Pipeline CI/CD",
            "",
        ]
        for stage in stages:
            lines.append(f"- {stage}")

        lines += ["", "## Stratégie de rollback", "", f"> {rollback}", "", "## Health Checks", ""]
        for chk in health:
            lines.append(f"- {chk}")

        lines += ["", "## Alerting", ""]
        for k, v in monitoring.get("alerting", {}).items():
            lines.append(f"- **{k}**: {v}")

        lines += ["", "## Dashboards de monitoring", ""]
        for d in monitoring.get("dashboards", []):
            lines.append(f"- {d}")

        return "\n".join(lines)
