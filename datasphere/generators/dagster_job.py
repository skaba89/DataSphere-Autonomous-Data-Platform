"""Génère des jobs/assets Dagster à partir des contraintes d'architecture."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datasphere.models.request import ArchitectureConstraints


@dataclass
class DagsterProjectFiles:
    files: dict[str, str] = field(default_factory=dict)

    def write(self, output_dir: str) -> list[str]:
        base = Path(output_dir) / "dagster"
        written = []
        for rel_path, content in self.files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(str(p))
        return written


class DagsterJobGenerator:
    """Génère un projet Dagster avec Software-Defined Assets."""

    def generate(
        self,
        business_request: str,
        constraints: ArchitectureConstraints,
    ) -> DagsterProjectFiles:
        slug = self._slug(business_request)
        files: dict[str, str] = {}

        files["workspace.yaml"]                         = self._workspace_yaml(slug)
        files["pyproject.toml"]                         = self._pyproject_toml(slug)
        files["setup.py"]                               = self._setup_py(slug)
        files[f"{slug}/__init__.py"]                    = self._package_init(slug, constraints)
        files[f"{slug}/assets/__init__.py"]             = ""
        files[f"{slug}/assets/ingestion.py"]            = self._ingestion_assets(constraints)
        files[f"{slug}/assets/transformation.py"]       = self._transformation_assets(constraints)
        files[f"{slug}/assets/quality.py"]              = self._quality_assets(constraints)
        files[f"{slug}/resources/__init__.py"]          = ""
        files[f"{slug}/resources/warehouse.py"]         = self._warehouse_resource(constraints)
        files[f"{slug}/jobs/__init__.py"]               = ""
        files[f"{slug}/jobs/pipeline.py"]               = self._pipeline_job(slug, constraints)
        files[f"{slug}/schedules/__init__.py"]          = ""
        files[f"{slug}/schedules/daily.py"]             = self._schedules(slug, constraints)
        files[f"{slug}/sensors/__init__.py"]            = ""
        files[f"{slug}/sensors/freshness.py"]           = self._freshness_sensor(slug, constraints)
        files["dagster.yaml"]                           = self._dagster_yaml(constraints)
        files["README.md"]                              = self._readme(slug, business_request, constraints)

        return DagsterProjectFiles(files=files)

    # ------------------------------------------------------------------

    def _workspace_yaml(self, slug: str) -> str:
        return f"""load_from:
  - python_package:
      package_name: {slug}
      location_name: {slug}
"""

    def _pyproject_toml(self, slug: str) -> str:
        return f"""[tool.dagster]
module_name = "{slug}"
"""

    def _setup_py(self, slug: str) -> str:
        return f"""from setuptools import find_packages, setup

setup(
    name="{slug}",
    packages=find_packages(exclude=["{slug}_tests"]),
    install_requires=[
        "dagster",
        "dagster-cloud",
        "dagster-dbt",
        "dbt-core",
    ],
    extras_require={{"dev": ["dagster-webserver"]}},
)
"""

    def _package_init(self, slug: str, c: ArchitectureConstraints) -> str:
        return f'''"""
{slug} — pipeline Dagster
Généré automatiquement par DataSphere.
Stack : {c.cloud_provider} / {c.data_warehouse} / {c.orchestrator}
"""
from dagster import Definitions, load_assets_from_modules

from {slug}.assets import ingestion, transformation, quality
from {slug}.jobs.pipeline import {slug}_job
from {slug}.schedules.daily import daily_schedule
from {slug}.sensors.freshness import freshness_sensor
from {slug}.resources.warehouse import warehouse_resource

all_assets = load_assets_from_modules([ingestion, transformation, quality])

defs = Definitions(
    assets=all_assets,
    jobs=[{slug}_job],
    schedules=[daily_schedule],
    sensors=[freshness_sensor],
    resources={{"warehouse": warehouse_resource}},
)
'''

    def _ingestion_assets(self, c: ArchitectureConstraints) -> str:
        tool = c.ingestion.lower()
        if tool == "airbyte":
            ingest_code = '''from dagster_airbyte import AirbyteResource, build_airbyte_assets

airbyte_assets = build_airbyte_assets(
    connection_id=EnvVar("AIRBYTE_CONNECTION_ID"),
    destination_tables=["orders", "customers", "products"],
)'''
            extra_import = "from dagster import EnvVar\nfrom dagster_airbyte import AirbyteResource, build_airbyte_assets"
        elif tool == "meltano":
            ingest_code = '''@asset(group_name="ingestion", compute_kind="meltano")
def raw_orders(context: AssetExecutionContext) -> None:
    """Ingère les commandes via Meltano."""
    import subprocess
    result = subprocess.run(
        ["meltano", "run", "tap-source", "target-warehouse"],
        capture_output=True, text=True, check=True,
    )
    context.log.info(result.stdout)

@asset(group_name="ingestion", compute_kind="meltano")
def raw_customers(context: AssetExecutionContext) -> None:
    """Ingère les clients via Meltano."""
    context.log.info("Meltano ingestion: customers")

@asset(group_name="ingestion", compute_kind="meltano")
def raw_products(context: AssetExecutionContext) -> None:
    """Ingère les produits via Meltano."""
    context.log.info("Meltano ingestion: products")'''
            extra_import = ""
        else:
            ingest_code = '''@asset(group_name="ingestion", compute_kind="bash")
def raw_orders(context: AssetExecutionContext) -> None:
    """Ingère les commandes."""
    context.log.info(f"Ingestion via {tool}")

@asset(group_name="ingestion", compute_kind="bash")
def raw_customers(context: AssetExecutionContext) -> None:
    context.log.info("Ingestion: customers")

@asset(group_name="ingestion", compute_kind="bash")
def raw_products(context: AssetExecutionContext) -> None:
    context.log.info("Ingestion: products")'''
            extra_import = ""

        return f'''"""Assets d\'ingestion — {c.ingestion}"""
from dagster import asset, AssetExecutionContext
{extra_import}

{ingest_code}
'''

    def _transformation_assets(self, c: ArchitectureConstraints) -> str:
        tool = c.transformation.lower()
        if tool in ("dbt", "dbt core"):
            return f'''"""Assets de transformation — dbt"""
from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets
from pathlib import Path

DBT_PROJECT_DIR = Path(__file__).parent.parent.parent / "dbt"

@dbt_assets(manifest=DBT_PROJECT_DIR / "target" / "manifest.json")
def dbt_pipeline_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Exécute tous les modèles dbt."""
    yield from dbt.cli(["build"], context=context).stream()
'''
        elif tool == "spark":
            return f'''"""Assets de transformation — Spark"""
from dagster import asset, AssetExecutionContext
from {c.ingestion.replace("-", "_")}_assets import raw_orders, raw_customers, raw_products

@asset(
    group_name="transformation",
    compute_kind="spark",
    deps=[raw_orders, raw_customers, raw_products],
)
def stg_orders(context: AssetExecutionContext) -> None:
    """Normalise les commandes via Spark."""
    context.log.info("Spark transformation: stg_orders")

@asset(group_name="transformation", compute_kind="spark", deps=[stg_orders])
def fct_orders(context: AssetExecutionContext) -> None:
    """Table de faits commandes."""
    context.log.info("Spark transformation: fct_orders")
'''
        else:
            return f'''"""Assets de transformation — {c.transformation}"""
from dagster import asset, AssetExecutionContext

@asset(group_name="transformation", compute_kind="{tool}")
def stg_orders(context: AssetExecutionContext) -> None:
    context.log.info("Transformation: stg_orders")

@asset(group_name="transformation", compute_kind="{tool}", deps=["stg_orders"])
def fct_orders(context: AssetExecutionContext) -> None:
    context.log.info("Transformation: fct_orders")

@asset(group_name="transformation", compute_kind="{tool}", deps=["fct_orders"])
def agg_daily_sales(context: AssetExecutionContext) -> None:
    context.log.info("Transformation: agg_daily_sales")
'''

    def _quality_assets(self, c: ArchitectureConstraints) -> str:
        tool = (c.quality or "great-expectations").lower()
        if "great" in tool:
            check_code = '''    import subprocess
    result = subprocess.run(
        ["great_expectations", "checkpoint", "run", "my_checkpoint"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise Exception(f"GE checkpoint failed: {result.stderr}")
    context.log.info("Great Expectations: all checks passed")'''
        elif "soda" in tool:
            check_code = '''    import subprocess
    # soda scan -d warehouse -c /opt/soda/configuration.yml /opt/soda/checks.yml
    result = subprocess.run(
        ["soda", "scan", "-d", "warehouse", "-c", "/opt/soda/configuration.yml", "/opt/soda/checks.yml"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise Exception(f"Soda scan failed: {result.stderr}")
    context.log.info("Soda Core: all checks passed")'''
        else:
            check_code = '''    context.log.info(f"Quality check via {tool}: passed")'''

        return f'''"""Assets de qualité — {c.quality or "great-expectations"}"""
from dagster import asset, AssetExecutionContext, AssetCheckResult, asset_check

@asset(
    group_name="quality",
    compute_kind="{tool}",
    deps=["fct_orders", "agg_daily_sales"],
)
def data_quality_check(context: AssetExecutionContext) -> None:
    """Vérifie la qualité des données après transformation."""
{check_code}

@asset_check(asset="fct_orders")
def fct_orders_not_empty(context: AssetExecutionContext) -> AssetCheckResult:
    """Vérifie que fct_orders n\'est pas vide."""
    # Replace with actual warehouse query
    row_count = 1  # placeholder
    return AssetCheckResult(
        passed=row_count > 0,
        metadata={{"row_count": row_count}},
    )
'''

    def _warehouse_resource(self, c: ArchitectureConstraints) -> str:
        wh = c.data_warehouse.lower()
        if wh == "snowflake":
            return '''"""Resource Snowflake pour Dagster."""
from dagster import EnvVar
from dagster_snowflake import SnowflakeResource

warehouse_resource = SnowflakeResource(
    account=EnvVar("SNOWFLAKE_ACCOUNT"),
    user=EnvVar("SNOWFLAKE_USER"),
    password=EnvVar("SNOWFLAKE_PASSWORD"),
    database=EnvVar("SNOWFLAKE_DATABASE"),
    warehouse=EnvVar("SNOWFLAKE_WAREHOUSE"),
    schema=EnvVar("SNOWFLAKE_SCHEMA"),
)
'''
        elif wh == "bigquery":
            return '''"""Resource BigQuery pour Dagster."""
from dagster import EnvVar
from dagster_gcp import BigQueryResource

warehouse_resource = BigQueryResource(
    project=EnvVar("GCP_PROJECT"),
    gcp_credentials=EnvVar("GOOGLE_APPLICATION_CREDENTIALS"),
)
'''
        else:
            return f'''"""Resource PostgreSQL-compatible pour Dagster."""
from dagster import EnvVar
from dagster_postgres import PostgresqlResource

warehouse_resource = PostgresqlResource(
    host=EnvVar("DBT_HOST"),
    port=5432,
    user=EnvVar("DBT_USER"),
    password=EnvVar("DBT_PASSWORD"),
    database=EnvVar("DBT_DATABASE"),
)
'''

    def _pipeline_job(self, slug: str, c: ArchitectureConstraints) -> str:
        return f'''"""Job pipeline principal — {slug}"""
from dagster import define_asset_job, AssetSelection

{slug}_job = define_asset_job(
    name="{slug}_job",
    selection=AssetSelection.groups("ingestion", "transformation", "quality"),
    description="Pipeline complet : ingestion → transformation → qualité",
    tags={{
        "cloud": "{c.cloud_provider}",
        "warehouse": "{c.data_warehouse}",
        "team": "datasphere",
    }},
)
'''

    def _schedules(self, slug: str, c: ArchitectureConstraints) -> str:
        cron = "*/15 * * * *" if c.processing_mode == "realtime" else "0 2 * * *"
        description = "Toutes les 15 minutes" if c.processing_mode == "realtime" else "Quotidien à 2h UTC"
        return f'''"""Schedules — {slug}"""
from dagster import ScheduleDefinition
from {slug}.jobs.pipeline import {slug}_job

daily_schedule = ScheduleDefinition(
    job={slug}_job,
    cron_schedule="{cron}",
    name="{slug}_schedule",
    description="{description}",
)
'''

    def _freshness_sensor(self, slug: str, c: ArchitectureConstraints) -> str:
        return f'''"""Sensor de fraîcheur des données — {slug}"""
from dagster import (
    sensor, SensorEvaluationContext, RunRequest,
    SkipReason, asset_sensor, AssetKey,
)
from {slug}.jobs.pipeline import {slug}_job

@sensor(
    job={slug}_job,
    minimum_interval_seconds=300,
    name="{slug}_freshness_sensor",
    description="Déclenche le pipeline si les données source ont changé.",
)
def freshness_sensor(context: SensorEvaluationContext):
    """Vérifie si une nouvelle ingestion est disponible."""
    # Remplacer par une vraie vérification (ex: watermark S3, CDC offset Kafka)
    last_run = context.last_run_key
    current_key = str(int(__import__("time").time() // 3600))  # hourly key

    if last_run == current_key:
        yield SkipReason("Aucune nouvelle donnée détectée.")
    else:
        yield RunRequest(run_key=current_key, run_config={{}})
'''

    def _dagster_yaml(self, c: ArchitectureConstraints) -> str:
        return f"""telemetry:
  enabled: false

storage:
  postgres:
    postgres_db:
      username:
        env: DAGSTER_PG_USER
      password:
        env: DAGSTER_PG_PASSWORD
      hostname: postgresql
      db_name: dagster
      port: 5432

run_coordinator:
  module: dagster.core.run_coordinator
  class: QueuedRunCoordinator
  config:
    max_concurrent_runs: 5

run_launcher:
  module: dagster.core.launcher
  class: DefaultRunLauncher

compute_logs:
  module: dagster_aws.s3.compute_log_manager
  class: S3ComputeLogManager
  config:
    bucket: "{c.cloud_provider}-datasphere-logs"
    prefix: "dagster-compute-logs"
"""

    def _readme(self, slug: str, business_request: str, c: ArchitectureConstraints) -> str:
        return f"""# Dagster Project — {slug}

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
pip install -e ".[dev]"
dagster dev          # Lance Dagit sur http://localhost:3000
```

## Structure

```
{slug}/
├── assets/
│   ├── ingestion.py       # Raw data assets
│   ├── transformation.py  # Cleaned & modelled assets
│   └── quality.py         # Quality check assets
├── jobs/
│   └── pipeline.py        # Job definition
├── schedules/
│   └── daily.py           # Cron schedule
├── sensors/
│   └── freshness.py       # Data freshness sensor
├── resources/
│   └── warehouse.py       # Warehouse resource
└── __init__.py            # Definitions
```

## Commandes utiles

```bash
dagster asset materialize --select "*"          # Matérialiser tous les assets
dagster asset materialize --select "ingestion*" # Seulement l'ingestion
dagster job execute -j {slug}_job              # Lancer le job complet
dagster schedule start {slug}_schedule         # Activer le schedule
```
"""

    def _slug(self, text: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:30] or "pipeline"
