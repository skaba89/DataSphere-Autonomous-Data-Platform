"""Tests pour les générateurs dbt et Airflow DAG."""
import pytest
from datasphere.models.request import ArchitectureConstraints
from datasphere.generators.dbt_project import DbtProjectGenerator
from datasphere.generators.airflow_dag import AirflowDagGenerator


def _constraints(
    cloud="aws", wh="snowflake", orch="airflow",
    ingest="airbyte", transform="dbt", bi="superset",
    quality="great-expectations", budget="enterprise",
    mode="batch",
) -> ArchitectureConstraints:
    return ArchitectureConstraints(
        cloud_provider=cloud,
        data_warehouse=wh,
        orchestrator=orch,
        ingestion=ingest,
        transformation=transform,
        bi_tool=bi,
        deployment="kubernetes",
        security=["RBAC"],
        budget=budget,
        data_lake="s3",
        catalog="openmetadata",
        quality=quality,
        processing_mode=mode,
    )


# ---------------------------------------------------------------------------
# dbt project generator
# ---------------------------------------------------------------------------

class TestDbtProjectGenerator:

    def test_generates_core_files(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Analyse des ventes", c)
        assert "dbt_project.yml" in project.files
        assert "profiles.yml" in project.files
        assert "packages.yml" in project.files
        assert ".sqlfluff" in project.files

    def test_all_warehouses_get_profile(self):
        warehouses = ["postgresql", "snowflake", "bigquery", "redshift",
                      "databricks", "azure-synapse", "clickhouse", "duckdb"]
        for wh in warehouses:
            c = _constraints(wh=wh)
            project = DbtProjectGenerator().generate("Test", c)
            profiles = project.files["profiles.yml"]
            assert "type:" in profiles, f"No type in profiles for {wh}"

    def test_staging_models_generated(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Analyse ventes", c)
        staging_files = [k for k in project.files if "staging" in k and k.endswith(".sql")]
        assert len(staging_files) >= 3
        assert any("stg_orders" in k for k in staging_files)
        assert any("stg_customers" in k for k in staging_files)

    def test_mart_models_generated(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Analyse ventes", c)
        mart_files = [k for k in project.files if "marts" in k and k.endswith(".sql")]
        assert len(mart_files) >= 3
        assert any("fct_orders" in k for k in mart_files)
        assert any("dim_customers" in k for k in mart_files)
        assert any("agg_daily" in k for k in mart_files)

    def test_dbt_project_yml_content(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Analyse ventes", c)
        yml = project.files["dbt_project.yml"]
        assert "staging:" in yml
        assert "marts:" in yml
        assert "materialized: view" in yml
        assert "materialized: table" in yml

    def test_sources_yml_references_ingestion_tool(self):
        c = _constraints(ingest="meltano")
        project = DbtProjectGenerator().generate("Test", c)
        sources = project.files["models/staging/sources.yml"]
        assert "meltano" in sources

    def test_exposures_yml_references_bi_tool(self):
        c = _constraints(bi="metabase")
        project = DbtProjectGenerator().generate("Test", c)
        exposures = project.files["models/exposures.yml"]
        assert "metabase" in exposures

    def test_macros_generated(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Test", c)
        assert "macros/generate_schema_name.sql" in project.files
        assert "macros/audit_helper.sql" in project.files

    def test_gitignore_excludes_target(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Test", c)
        gitignore = project.files[".gitignore"]
        assert "target/" in gitignore
        assert "profiles.yml" in gitignore

    def test_write_to_disk(self, tmp_path):
        c = _constraints()
        project = DbtProjectGenerator().generate("Test pipeline", c)
        written = project.write(str(tmp_path))
        assert len(written) >= 10
        assert (tmp_path / "dbt" / "dbt_project.yml").exists()
        assert (tmp_path / "dbt" / "profiles.yml").exists()
        assert (tmp_path / "dbt" / "models" / "marts" / "fct_orders.sql").exists()

    def test_project_name_slugified(self):
        gen = DbtProjectGenerator()
        assert gen._project_name("Analyse les ventes 2024") == "analyse_les_ventes_2024"
        assert gen._project_name("Données hospitalières — patients") == "donn_es_hospitali_res_patients"

    def test_sqlfluff_dialect_matches_warehouse(self):
        mapping = {
            "snowflake": "snowflake",
            "bigquery": "bigquery",
            "postgresql": "postgres",
            "azure-synapse": "tsql",
        }
        for wh, expected_dialect in mapping.items():
            c = _constraints(wh=wh)
            project = DbtProjectGenerator().generate("Test", c)
            sqlfluff = project.files[".sqlfluff"]
            assert expected_dialect in sqlfluff, f"Dialect {expected_dialect} not found for {wh}"

    def test_snowflake_profile_has_account_field(self):
        c = _constraints(wh="snowflake")
        project = DbtProjectGenerator().generate("Test", c)
        profiles = project.files["profiles.yml"]
        assert "account:" in profiles
        assert "warehouse:" in profiles

    def test_bigquery_profile_has_project_field(self):
        c = _constraints(wh="bigquery", cloud="gcp")
        project = DbtProjectGenerator().generate("Test", c)
        profiles = project.files["profiles.yml"]
        assert "project:" in profiles
        assert "dataset:" in profiles

    def test_fct_orders_uses_dbt_utils_surrogate_key(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Test", c)
        fct = project.files["models/marts/fct_orders.sql"]
        assert "generate_surrogate_key" in fct

    def test_schema_yml_has_not_null_tests(self):
        c = _constraints()
        project = DbtProjectGenerator().generate("Test", c)
        schema_files = [v for k, v in project.files.items() if "schema.yml" in k]
        all_content = "\n".join(schema_files)
        assert "not_null" in all_content
        assert "unique" in all_content


# ---------------------------------------------------------------------------
# Airflow DAG generator
# ---------------------------------------------------------------------------

class TestAirflowDagGenerator:

    def test_generates_main_and_quality_dags(self):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Analyse ventes", c)
        dag_files = [k for k in dags.files if k.endswith(".py")]
        assert len(dag_files) == 2
        assert any("pipeline" in k for k in dag_files)
        assert any("quality" in k for k in dag_files)

    def test_main_dag_has_correct_structure(self):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Analyse ventes", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "with DAG(" in pipeline
        assert "dag_id=" in pipeline
        assert "default_args" in pipeline
        assert "start >> ingest" in pipeline

    def test_quality_dag_has_external_sensor(self):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Analyse ventes", c)
        quality = next(v for k, v in dags.files.items() if "quality" in k)
        assert "ExternalTaskSensor" in quality
        assert "wait_for_" in quality

    def test_batch_mode_daily_schedule(self):
        c = _constraints(mode="batch")
        dags = AirflowDagGenerator().generate("Analyse ventes", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "0 2 * * *" in pipeline

    def test_realtime_mode_frequent_schedule(self):
        c = _constraints(mode="realtime")
        dags = AirflowDagGenerator().generate("Flux temps réel", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "*/15" in pipeline

    def test_airbyte_uses_airbyte_operator(self):
        c = _constraints(ingest="airbyte")
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "AirbyteTriggerSyncOperator" in pipeline

    def test_meltano_uses_bash_operator(self):
        c = _constraints(ingest="meltano")
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "meltano run" in pipeline

    def test_dbt_transformation_uses_bash(self):
        c = _constraints(transform="dbt")
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "dbt run" in pipeline
        assert "dbt test" in pipeline

    def test_spark_transformation_uses_spark_operator(self):
        c = _constraints(transform="spark")
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "SparkSubmitOperator" in pipeline

    def test_dag_has_failure_notification(self):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "notify_failure" in pipeline
        assert "ONE_FAILED" in pipeline or "one_failed" in pipeline

    def test_soda_core_quality_operator(self):
        c = _constraints(quality="soda-core")
        dags = AirflowDagGenerator().generate("Test", c)
        quality = next(v for k, v in dags.files.items() if "quality" in k)
        assert "soda scan" in quality

    def test_config_files_generated(self):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Test", c)
        assert "config/variables.json" in dags.files
        assert "config/connections.json" in dags.files

    def test_variables_json_is_valid_json(self):
        import json
        c = _constraints()
        dags = AirflowDagGenerator().generate("Test", c)
        data = json.loads(dags.files["config/variables.json"])
        assert "airbyte_connection_id" in data
        assert "dbt_project_dir" in data

    def test_connections_json_has_warehouse_entry(self):
        import json
        c = _constraints(wh="postgresql")
        dags = AirflowDagGenerator().generate("Test", c)
        connections = json.loads(dags.files["config/connections.json"])
        assert any("postgresql" in conn["conn_id"] for conn in connections)

    def test_write_to_disk(self, tmp_path):
        c = _constraints()
        dags = AirflowDagGenerator().generate("Test pipeline", c)
        written = dags.write(str(tmp_path))
        assert len(written) >= 3
        dag_py_files = [f for f in written if f.endswith(".py")]
        assert len(dag_py_files) == 2

    def test_dag_tags_include_cloud_and_warehouse(self):
        c = _constraints(cloud="gcp", wh="bigquery")
        dags = AirflowDagGenerator().generate("Test", c)
        pipeline = next(v for k, v in dags.files.items() if "pipeline" in k)
        assert "gcp" in pipeline
        assert "bigquery" in pipeline
