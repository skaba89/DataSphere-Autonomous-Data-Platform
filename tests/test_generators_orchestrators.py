"""Tests pour les générateurs Dagster et Prefect."""
import pytest
from datasphere.models.request import ArchitectureConstraints
from datasphere.generators.dagster_job import DagsterJobGenerator
from datasphere.generators.prefect_flow import PrefectFlowGenerator


def _c(cloud="aws", wh="snowflake", orch="dagster", ingest="airbyte",
        transform="dbt", bi="superset", quality="great-expectations",
        budget="enterprise", mode="batch") -> ArchitectureConstraints:
    return ArchitectureConstraints(
        cloud_provider=cloud, data_warehouse=wh, orchestrator=orch,
        ingestion=ingest, transformation=transform, bi_tool=bi,
        deployment="kubernetes", security=["RBAC"], budget=budget,
        data_lake="s3", catalog="openmetadata", quality=quality,
        processing_mode=mode,
    )


# -----------------------------------------------------------------------
# Dagster
# -----------------------------------------------------------------------

class TestDagsterJobGenerator:

    def test_generates_core_files(self):
        c = _c()
        project = DagsterJobGenerator().generate("Analyse ventes", c)
        assert "workspace.yaml" in project.files
        assert "dagster.yaml" in project.files
        assert "pyproject.toml" in project.files
        assert "setup.py" in project.files

    def test_generates_assets_and_jobs(self):
        c = _c()
        project = DagsterJobGenerator().generate("Analyse ventes", c)
        files = project.files
        assert any("assets/ingestion.py" in k for k in files)
        assert any("assets/transformation.py" in k for k in files)
        assert any("assets/quality.py" in k for k in files)
        assert any("jobs/pipeline.py" in k for k in files)

    def test_generates_schedules_and_sensors(self):
        c = _c()
        project = DagsterJobGenerator().generate("Test", c)
        assert any("schedules/daily.py" in k for k in project.files)
        assert any("sensors/freshness.py" in k for k in project.files)

    def test_package_init_has_definitions(self):
        c = _c()
        project = DagsterJobGenerator().generate("Analyse ventes", c)
        init_file = next(v for k, v in project.files.items() if k.endswith("/__init__.py") and "defs" in v)
        assert "Definitions" in init_file
        assert "dbt_pipeline_assets" in init_file or "all_assets" in init_file

    def test_dbt_transformation_uses_dagster_dbt(self):
        c = _c(transform="dbt")
        project = DagsterJobGenerator().generate("Test", c)
        transform = next(v for k, v in project.files.items() if "transformation" in k)
        assert "dbt_assets" in transform or "DbtCliResource" in transform

    def test_spark_transformation_uses_spark_operator(self):
        c = _c(transform="spark")
        project = DagsterJobGenerator().generate("Test", c)
        transform = next(v for k, v in project.files.items() if "transformation" in k)
        assert "spark" in transform.lower()

    def test_meltano_ingestion_uses_subprocess(self):
        c = _c(ingest="meltano")
        project = DagsterJobGenerator().generate("Test", c)
        ingestion = next(v for k, v in project.files.items() if "ingestion" in k)
        assert "meltano" in ingestion.lower()

    def test_airbyte_ingestion_uses_airbyte_asset(self):
        c = _c(ingest="airbyte")
        project = DagsterJobGenerator().generate("Test", c)
        ingestion = next(v for k, v in project.files.items() if "ingestion" in k)
        assert "airbyte" in ingestion.lower()

    def test_soda_quality_uses_soda_command(self):
        c = _c(quality="soda-core")
        project = DagsterJobGenerator().generate("Test", c)
        quality = next(v for k, v in project.files.items() if "quality" in k)
        assert "soda scan" in quality

    def test_realtime_schedule_is_frequent(self):
        c = _c(mode="realtime")
        project = DagsterJobGenerator().generate("Flux temps réel", c)
        schedule = next(v for k, v in project.files.items() if "daily.py" in k)
        assert "*/15" in schedule

    def test_batch_schedule_is_daily(self):
        c = _c(mode="batch")
        project = DagsterJobGenerator().generate("Test", c)
        schedule = next(v for k, v in project.files.items() if "daily.py" in k)
        assert "0 2 * * *" in schedule

    def test_snowflake_resource_uses_snowflake(self):
        c = _c(wh="snowflake")
        project = DagsterJobGenerator().generate("Test", c)
        resource = next(v for k, v in project.files.items() if "warehouse.py" in k)
        assert "SnowflakeResource" in resource

    def test_bigquery_resource_uses_bigquery(self):
        c = _c(wh="bigquery", cloud="gcp")
        project = DagsterJobGenerator().generate("Test", c)
        resource = next(v for k, v in project.files.items() if "warehouse.py" in k)
        assert "BigQueryResource" in resource

    def test_asset_check_generated(self):
        c = _c()
        project = DagsterJobGenerator().generate("Test", c)
        quality = next(v for k, v in project.files.items() if "quality.py" in k)
        assert "asset_check" in quality or "AssetCheckResult" in quality

    def test_job_has_correct_tags(self):
        c = _c(cloud="gcp", wh="bigquery")
        project = DagsterJobGenerator().generate("Test", c)
        job_file = next(v for k, v in project.files.items() if "jobs/pipeline.py" in k)
        assert "gcp" in job_file
        assert "bigquery" in job_file

    def test_write_to_disk(self, tmp_path):
        c = _c()
        project = DagsterJobGenerator().generate("Test pipeline", c)
        written = project.write(str(tmp_path))
        assert len(written) >= 8
        assert (tmp_path / "dagster" / "workspace.yaml").exists()

    def test_readme_generated(self):
        c = _c()
        project = DagsterJobGenerator().generate("Test", c)
        assert "README.md" in project.files
        readme = project.files["README.md"]
        assert "dagster dev" in readme
        assert "snowflake" in readme.lower()


# -----------------------------------------------------------------------
# Prefect
# -----------------------------------------------------------------------

class TestPrefectFlowGenerator:

    def test_generates_core_files(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Analyse ventes", c)
        assert "prefect.yaml" in flows.files
        assert "deployments.yaml" in flows.files
        assert "blocks/setup_blocks.py" in flows.files

    def test_generates_two_flows(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Analyse ventes", c)
        py_files = [k for k in flows.files if k.endswith(".py") and "flows/" in k]
        assert len(py_files) == 2
        assert any("pipeline" in k for k in py_files)
        assert any("quality" in k for k in py_files)

    def test_main_flow_has_correct_structure(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Analyse ventes", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "@flow" in pipeline
        assert "@task" in pipeline
        assert "ingest_data" in pipeline
        assert "transform_data" in pipeline

    def test_flow_has_retry_config(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Test", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "retries=" in pipeline
        assert "retry_delay_seconds=" in pipeline

    def test_batch_schedule_in_deployments(self):
        c = _c(orch="prefect", mode="batch")
        flows = PrefectFlowGenerator().generate("Test", c)
        depl = flows.files["deployments.yaml"]
        assert "0 2 * * *" in depl

    def test_realtime_schedule_in_deployments(self):
        c = _c(orch="prefect", mode="realtime")
        flows = PrefectFlowGenerator().generate("Test", c)
        depl = flows.files["deployments.yaml"]
        assert "*/15" in depl

    def test_quality_flow_uses_correct_tool(self):
        c = _c(orch="prefect", quality="soda-core")
        flows = PrefectFlowGenerator().generate("Test", c)
        quality = next(v for k, v in flows.files.items() if "quality" in k)
        assert "soda scan" in quality

    def test_airbyte_task_in_pipeline(self):
        c = _c(orch="prefect", ingest="airbyte")
        flows = PrefectFlowGenerator().generate("Test", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "airbyte" in pipeline.lower()

    def test_meltano_task_in_pipeline(self):
        c = _c(orch="prefect", ingest="meltano")
        flows = PrefectFlowGenerator().generate("Test", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "meltano run" in pipeline

    def test_dbt_task_in_pipeline(self):
        c = _c(orch="prefect", transform="dbt")
        flows = PrefectFlowGenerator().generate("Test", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "dbt run" in pipeline

    def test_snowflake_block_in_setup(self):
        c = _c(orch="prefect", wh="snowflake")
        flows = PrefectFlowGenerator().generate("Test", c)
        blocks = flows.files["blocks/setup_blocks.py"]
        assert "SnowflakeCredentials" in blocks or "snowflake" in blocks.lower()

    def test_bigquery_block_in_setup(self):
        c = _c(orch="prefect", wh="bigquery", cloud="gcp")
        flows = PrefectFlowGenerator().generate("Test", c)
        blocks = flows.files["blocks/setup_blocks.py"]
        assert "GcpCredentials" in blocks

    def test_slack_webhook_in_setup(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Test", c)
        blocks = flows.files["blocks/setup_blocks.py"]
        assert "SlackWebhook" in blocks

    def test_slack_notification_in_pipeline(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Test", c)
        pipeline = next(v for k, v in flows.files.items() if "pipeline" in k)
        assert "send_notification" in pipeline

    def test_write_to_disk(self, tmp_path):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Test pipeline", c)
        written = flows.write(str(tmp_path))
        assert len(written) >= 4
        assert (tmp_path / "prefect" / "prefect.yaml").exists()

    def test_readme_generated(self):
        c = _c(orch="prefect")
        flows = PrefectFlowGenerator().generate("Test", c)
        assert "README.md" in flows.files
        readme = flows.files["README.md"]
        assert "prefect deploy" in readme
