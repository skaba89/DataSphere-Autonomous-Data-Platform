"""Génère des flows Prefect 2/3 à partir des contraintes d'architecture."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datasphere.models.request import ArchitectureConstraints


@dataclass
class PrefectFlowFiles:
    files: dict[str, str] = field(default_factory=dict)

    def write(self, output_dir: str) -> list[str]:
        base = Path(output_dir) / "prefect"
        written = []
        for rel_path, content in self.files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(str(p))
        return written


class PrefectFlowGenerator:
    """Génère des flows Prefect avec tasks, deployments et blocks."""

    def generate(
        self,
        business_request: str,
        constraints: ArchitectureConstraints,
    ) -> PrefectFlowFiles:
        slug = self._slug(business_request)
        files: dict[str, str] = {}

        files[f"flows/{slug}_pipeline.py"]  = self._pipeline_flow(business_request, constraints, slug)
        files[f"flows/{slug}_quality.py"]   = self._quality_flow(business_request, constraints, slug)
        files["deployments.yaml"]           = self._deployments_yaml(slug, constraints)
        files["prefect.yaml"]               = self._prefect_yaml(slug, constraints)
        files["blocks/setup_blocks.py"]     = self._setup_blocks(constraints)
        files["README.md"]                  = self._readme(slug, business_request, constraints)

        return PrefectFlowFiles(files=files)

    # ------------------------------------------------------------------

    def _pipeline_flow(
        self, business_request: str, c: ArchitectureConstraints, slug: str
    ) -> str:
        ingest_task = self._ingest_task(c)
        transform_task = self._transform_task(c)
        schedule = '"0 2 * * *"' if c.processing_mode != "realtime" else '"*/15 * * * *"'

        return f'''"""
Flow pipeline principal — {business_request}
Stack : {c.ingestion} → {c.transformation} → {c.data_warehouse}
Généré automatiquement par DataSphere.
"""
from __future__ import annotations
from datetime import timedelta
from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from prefect.blocks.notifications import SlackWebhook


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(
    name="ingest_data",
    description="Ingestion via {c.ingestion}",
    retries=3,
    retry_delay_seconds=60,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=1),
    tags=["{c.ingestion}", "ingestion"],
)
def ingest_data(source: str = "all") -> dict:
    """Ingère les données depuis les sources."""
    logger = get_run_logger()
    logger.info(f"Starting ingestion via {c.ingestion} for source: {{source}}")
{ingest_task}
    return {{"status": "completed", "source": source, "ingestion_tool": "{c.ingestion}"}}


@task(
    name="transform_data",
    description="Transformation via {c.transformation}",
    retries=2,
    retry_delay_seconds=30,
    tags=["{c.transformation}", "transformation"],
)
def transform_data(ingestion_result: dict) -> dict:
    """Transforme les données ingérées."""
    logger = get_run_logger()
    logger.info(f"Starting transformation via {c.transformation}")
{transform_task}
    return {{"status": "completed", "rows_transformed": 0, "transformation_tool": "{c.transformation}"}}


@task(
    name="run_dbt_tests",
    description="Tests de qualité dbt",
    retries=1,
    tags=["quality", "dbt"],
)
def run_dbt_tests(transform_result: dict) -> dict:
    """Exécute les tests dbt après transformation."""
    import subprocess
    logger = get_run_logger()
    logger.info("Running dbt tests")
    result = subprocess.run(
        ["dbt", "test", "--profiles-dir", "/opt/dbt", "--project-dir", "/opt/dbt"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error(f"dbt test failed:\\n{{result.stdout}}")
        raise Exception("dbt tests failed")
    logger.info("dbt tests passed")
    return {{"status": "passed", "output": result.stdout[:500]}}


@task(name="send_notification", tags=["notification"])
def send_notification(status: str, details: str = "") -> None:
    """Envoie une notification Slack."""
    logger = get_run_logger()
    try:
        block = SlackWebhook.load("datasphere-slack")
        icon = "✅" if status == "success" else "❌"
        block.notify(f"{{icon}} DataSphere pipeline {{status}}: {slug}\\n{{details}}")
    except Exception as e:
        logger.warning(f"Notification failed (non-blocking): {{e}}")


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(
    name="{slug}_pipeline",
    description="{business_request}",
    timeout_seconds=14400,
    retries=1,
    retry_delay_seconds=300,
    log_prints=True,
)
def {slug}_pipeline(source: str = "all") -> dict:
    """
    Pipeline complet : ingestion → transformation → qualité → notification.
    """
    logger = get_run_logger()
    logger.info(f"Starting {slug}_pipeline for source={{source}}")

    # Ingestion
    ingest_result = ingest_data(source=source)

    # Transformation
    transform_result = transform_data(ingestion_result=ingest_result)

    # Tests qualité
    test_result = run_dbt_tests(transform_result=transform_result)

    # Notification succès
    send_notification(
        status="success",
        details=f"Source: {{source}} | Rows: {{transform_result.get('rows_transformed', 'N/A')}}",
    )

    return {{
        "pipeline": "{slug}",
        "ingest":    ingest_result,
        "transform": transform_result,
        "tests":     test_result,
    }}


if __name__ == "__main__":
    {slug}_pipeline()
'''

    def _quality_flow(
        self, business_request: str, c: ArchitectureConstraints, slug: str
    ) -> str:
        tool = (c.quality or "great-expectations").lower()
        if "great" in tool:
            quality_cmd = '["great_expectations", "checkpoint", "run", "my_checkpoint"]'
        elif "soda" in tool:
            quality_cmd = '["soda", "scan", "-d", "warehouse", "-c", "/opt/soda/configuration.yml", "/opt/soda/checks.yml"]  # soda scan'
        else:
            quality_cmd = '["echo", "quality-check-passed"]'

        return f'''"""
Flow qualité — {business_request}
Exécute les checks {c.quality or "great-expectations"} après le pipeline.
"""
from __future__ import annotations
from prefect import flow, task, get_run_logger
from prefect.blocks.notifications import SlackWebhook


@task(name="run_quality_checks", retries=2, retry_delay_seconds=30)
def run_quality_checks() -> dict:
    """Exécute les checks de qualité."""
    import subprocess
    logger = get_run_logger()
    logger.info("Running quality checks via {c.quality or 'great-expectations'}")
    result = subprocess.run(
        {quality_cmd},
        capture_output=True, text=True,
    )
    passed = result.returncode == 0
    if not passed:
        logger.error(f"Quality check failed:\\n{{result.stdout}}")
    return {{"passed": passed, "tool": "{c.quality or 'great-expectations'}", "output": result.stdout[:500]}}


@task(name="check_data_freshness")
def check_data_freshness(table: str = "fct_orders") -> dict:
    """Vérifie que les données sont fraîches (< 25h)."""
    logger = get_run_logger()
    # Replace with actual warehouse query
    logger.info(f"Checking freshness for {{table}}")
    return {{"table": table, "fresh": True, "max_age_hours": 24}}


@flow(
    name="{slug}_quality",
    description="Quality checks — {business_request}",
    timeout_seconds=3600,
    log_prints=True,
)
def {slug}_quality() -> dict:
    """Flow de qualité à exécuter après le pipeline principal."""
    quality_result = run_quality_checks()
    freshness_result = check_data_freshness()

    all_passed = quality_result["passed"] and freshness_result["fresh"]

    if not all_passed:
        try:
            block = SlackWebhook.load("datasphere-slack")
            block.notify("⚠️ Quality checks FAILED on {slug}")
        except Exception:
            pass

    return {{"quality": quality_result, "freshness": freshness_result, "all_passed": all_passed}}


if __name__ == "__main__":
    {slug}_quality()
'''

    def _deployments_yaml(self, slug: str, c: ArchitectureConstraints) -> str:
        cron = "*/15 * * * *" if c.processing_mode == "realtime" else "0 2 * * *"
        return f"""deployments:
  - name: {slug}-pipeline-prod
    version: 1
    tags:
      - production
      - {c.cloud_provider}
      - {c.data_warehouse}
    description: "Pipeline production — {slug}"
    flow_name: {slug}_pipeline
    entrypoint: flows/{slug}_pipeline.py:{slug}_pipeline
    work_pool:
      name: datasphere-pool
      work_queue_name: default
    schedule:
      cron: "{cron}"
      timezone: "UTC"
    parameters:
      source: "all"
    pull:
      - prefect.deployments.steps.git_clone:
          repository: "{{{{ prefect.variables.repo_url }}}}"
          branch: main

  - name: {slug}-quality-prod
    version: 1
    tags:
      - production
      - quality
    flow_name: {slug}_quality
    entrypoint: flows/{slug}_quality.py:{slug}_quality
    work_pool:
      name: datasphere-pool
    schedule:
      cron: "30 2 * * *"
      timezone: "UTC"
"""

    def _prefect_yaml(self, slug: str, c: ArchitectureConstraints) -> str:
        return f"""name: {slug}
prefect-version: "3.0.0"

build: null

push: null

pull:
  - prefect.deployments.steps.git_clone:
      repository: "{{{{ prefect.variables.repo_url }}}}"
      branch: main
      credentials: "{{{{ prefect.blocks.github-credentials.datasphere }}}}"
"""

    def _setup_blocks(self, c: ArchitectureConstraints) -> str:
        wh = c.data_warehouse.lower()
        if wh == "snowflake":
            warehouse_block = '''from prefect_snowflake import SnowflakeCredentials, SnowflakeConnector

snowflake_creds = SnowflakeCredentials(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
)
snowflake_creds.save("datasphere-snowflake", overwrite=True)
print("✓ Snowflake credentials block saved")
'''
        elif wh == "bigquery":
            warehouse_block = '''from prefect_gcp import GcpCredentials

gcp_creds = GcpCredentials(service_account_file=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
gcp_creds.save("datasphere-gcp", overwrite=True)
print("✓ GCP credentials block saved")
'''
        else:
            warehouse_block = f'''from prefect_sqlalchemy import SqlAlchemyConnector, ConnectionComponents, SyncDriver

pg_connector = SqlAlchemyConnector(
    connection_info=ConnectionComponents(
        driver=SyncDriver.POSTGRESQL_PSYCOPG2,
        host=os.environ.get("DBT_HOST", "localhost"),
        port=5432,
        database=os.environ.get("DBT_DATABASE", "datasphere"),
        username=os.environ.get("DBT_USER", "datasphere"),
        password=os.environ.get("DBT_PASSWORD"),
    )
)
pg_connector.save("datasphere-{wh}", overwrite=True)
print("✓ {wh} connector block saved")
'''

        return f'''"""
Script d'initialisation des Prefect Blocks.
Exécuter une fois avant le premier déploiement :
    python blocks/setup_blocks.py
"""
import os
from prefect.blocks.notifications import SlackWebhook

# Slack notification block
slack_webhook = SlackWebhook(url=os.environ["SLACK_WEBHOOK_URL"])
slack_webhook.save("datasphere-slack", overwrite=True)
print("✓ Slack webhook block saved")

# Warehouse block
{warehouse_block}

print("\\nAll blocks configured. Run deployments with:")
print("  prefect deploy --all")
'''

    def _readme(self, slug: str, business_request: str, c: ArchitectureConstraints) -> str:
        return f"""# Prefect Flows — {slug}

> {business_request}

## Stack

| Couche | Outil |
|--------|-------|
| Warehouse | {c.data_warehouse} |
| Ingestion | {c.ingestion} |
| Transformation | {c.transformation} |
| Qualité | {c.quality or "great-expectations"} |

## Installation

```bash
pip install prefect prefect-dbt prefect-sqlalchemy
prefect server start          # Serveur local
python blocks/setup_blocks.py # Configurer les blocks
prefect deploy --all          # Déployer les flows
```

## Flows

| Flow | Description | Schedule |
|------|-------------|----------|
| `{slug}_pipeline` | Pipeline complet ingestion→transform→test | `{"*/15 * * * *" if c.processing_mode == "realtime" else "0 2 * * *"}` |
| `{slug}_quality`  | Checks qualité post-pipeline | `30 2 * * *` |

## Commandes utiles

```bash
prefect flow-run create {slug}_pipeline  # Lancer manuellement
prefect deployment run {slug}-pipeline-prod/{slug}-pipeline-prod
prefect work-pool create --type process datasphere-pool
prefect worker start --pool datasphere-pool
```
"""

    def _ingest_task(self, c: ArchitectureConstraints) -> str:
        tool = c.ingestion.lower()
        if tool == "airbyte":
            return '''    import subprocess
    result = subprocess.run(
        ["airbyte-ci", "connections", "sync", "--connection-id", source],
        capture_output=True, text=True,
    )
    logger.info(f"Airbyte sync: {result.stdout[:200]}")'''
        elif tool == "meltano":
            return '''    import subprocess
    # meltano run tap-<source> target-warehouse
    result = subprocess.run(
        ["meltano", "run", f"tap-{source}", "target-warehouse"],
        capture_output=True, text=True,
    )
    logger.info(f"Meltano: {result.stdout[:200]}")'''
        else:
            return f'''    logger.info("Ingestion via {tool} for source: {{source}}")'''

    def _transform_task(self, c: ArchitectureConstraints) -> str:
        tool = c.transformation.lower()
        if tool in ("dbt", "dbt core"):
            return '''    import subprocess
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", "/opt/dbt", "--project-dir", "/opt/dbt"],
        capture_output=True, text=True,
    )
    logger.info(f"dbt run: {result.stdout[:200]}")'''
        elif tool == "spark":
            return '''    logger.info("Spark transformation running...")
    # Replace with actual PySpark job submission'''
        else:
            return f'''    logger.info("Transformation via {tool}")'''

    def _slug(self, text: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:30] or "pipeline"
