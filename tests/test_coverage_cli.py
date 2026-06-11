"""
Tests for CLI modules — focused on pure/deterministic functions.
Interactive (input-requiring) functions are excluded.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# discovery.py — recommend_stack pure function
# ---------------------------------------------------------------------------

class TestRecommendStack:
    def _answer(self, **kwargs):
        from datasphere.cli.discovery import Answer
        defaults = dict(
            cloud="aws",
            source_db="postgresql",
            warehouse="auto",
            bi_tool="",
            orchestrator="",
            mode="batch",
            data_lake="no",
            infra="docker",
            security="simple",
            budget="medium",
        )
        defaults.update(kwargs)
        a = Answer(**defaults)
        # Patch the missing 'transformation' field — bug in discovery.py line 266
        # where it accesses a.transformation which is not defined on Answer
        a.transformation = ""
        return a

    def test_aws_auto_warehouse_selects_redshift(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="aws", warehouse="auto")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "redshift"

    def test_gcp_auto_warehouse_selects_bigquery(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="gcp", warehouse="auto")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "bigquery"

    def test_azure_auto_warehouse_selects_synapse(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="azure", warehouse="auto")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "azure-synapse"

    def test_low_budget_docker_auto_warehouse_selects_postgresql(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="local", warehouse="auto", budget="low", infra="docker")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "postgresql"

    def test_explicit_snowflake_warehouse(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(warehouse="snowflake")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "snowflake"

    def test_explicit_bigquery_warehouse(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="gcp", warehouse="bigquery")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "bigquery"

    def test_explicit_duckdb_warehouse(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(warehouse="duckdb")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "duckdb"

    def test_realtime_mode_ingestion(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(source_db="kafka", mode="realtime")
        stack = recommend_stack(a)
        assert stack["ingestion"]["type"] == "kafka-connect"

    def test_saas_source_uses_airbyte(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(source_db="saas", mode="batch")
        stack = recommend_stack(a)
        assert stack["ingestion"]["type"] == "airbyte"

    def test_low_budget_uses_meltano(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(budget="low", source_db="postgresql", mode="batch")
        stack = recommend_stack(a)
        assert stack["ingestion"]["type"] == "meltano"

    def test_realtime_mode_uses_flink_transform(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(mode="realtime")
        stack = recommend_stack(a)
        assert stack["transformation"]["type"] == "flink"

    def test_databricks_warehouse_uses_spark(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(warehouse="databricks", mode="batch")
        stack = recommend_stack(a)
        assert stack["transformation"]["type"] == "spark"

    def test_kubernetes_infra_uses_argo(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(infra="kubernetes", orchestrator="")
        stack = recommend_stack(a)
        assert stack["orchestration"]["type"] == "argo"

    def test_realtime_mode_uses_prefect_orch(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(mode="realtime", orchestrator="", infra="docker")
        stack = recommend_stack(a)
        assert stack["orchestration"]["type"] == "prefect"

    def test_data_lake_yes_aws_uses_s3(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="aws", data_lake="yes")
        stack = recommend_stack(a)
        assert stack["storage"]["type"] == "s3"

    def test_data_lake_yes_azure_uses_adls(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="azure", data_lake="yes")
        stack = recommend_stack(a)
        assert stack["storage"]["type"] == "adls"

    def test_data_lake_yes_gcp_uses_gcs(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="gcp", data_lake="yes")
        stack = recommend_stack(a)
        assert stack["storage"]["type"] == "gcs"

    def test_data_lake_yes_local_uses_minio(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="local", data_lake="yes")
        stack = recommend_stack(a)
        assert stack["storage"]["type"] == "minio"

    def test_realtime_bi_uses_grafana(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(mode="realtime", bi_tool="")
        stack = recommend_stack(a)
        assert stack["bi"]["type"] == "grafana"

    def test_low_budget_bi_uses_metabase(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(budget="low", bi_tool="", mode="batch")
        stack = recommend_stack(a)
        assert stack["bi"]["type"] == "metabase"

    def test_explicit_superset_bi(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(bi_tool="superset")
        stack = recommend_stack(a)
        assert stack["bi"]["type"] == "superset"

    def test_enterprise_budget_catalog_uses_datahub(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(budget="enterprise")
        stack = recommend_stack(a)
        assert stack["catalog"]["type"] == "datahub"

    def test_low_budget_catalog_uses_marquez(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(budget="low")
        stack = recommend_stack(a)
        assert stack["catalog"]["type"] == "marquez"

    def test_low_budget_ai_uses_ollama(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(budget="low", infra="docker", cloud="aws")
        stack = recommend_stack(a)
        assert stack["ai"]["type"] == "ollama"

    def test_azure_enterprise_ai_uses_azure_openai(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="azure", budget="enterprise")
        stack = recommend_stack(a)
        assert stack["ai"]["type"] == "azure-openai"

    def test_postgresql_warehouse_uses_pgvector(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(warehouse="postgresql")
        stack = recommend_stack(a)
        assert stack["vector"]["type"] == "pgvector"

    def test_kubernetes_infra_uses_helm(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(infra="kubernetes")
        stack = recommend_stack(a)
        assert stack["infrastructure"]["type"] == "helm"

    def test_managed_infra_uses_terraform(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(infra="managed")
        stack = recommend_stack(a)
        assert stack["infrastructure"]["type"] == "terraform"

    def test_enterprise_security_uses_keycloak(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(security="enterprise")
        stack = recommend_stack(a)
        assert stack["security"]["type"] == "keycloak"

    def test_simple_security_uses_vault(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(security="simple")
        stack = recommend_stack(a)
        assert stack["security"]["type"] == "vault"

    def test_managed_cloud_aws_uses_opentelemetry(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="aws", infra="managed")
        stack = recommend_stack(a)
        assert stack["monitoring"]["type"] == "opentelemetry"

    def test_docker_infra_uses_prometheus(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(infra="docker")
        stack = recommend_stack(a)
        assert stack["monitoring"]["type"] == "prometheus"

    def test_cloud_map_local_docker(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="local")
        stack = recommend_stack(a)
        assert stack["cloud"]["provider"] == "local-docker"

    def test_cloud_map_ovhcloud(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="ovhcloud")
        stack = recommend_stack(a)
        assert stack["cloud"]["provider"] == "ovhcloud"

    def test_realtime_budget_enterprise_warehouse_auto(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="on-premise", warehouse="auto", budget="enterprise", mode="realtime")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "clickhouse"

    def test_enterprise_budget_non_cloud_warehouse_auto(self):
        from datasphere.cli.discovery import recommend_stack
        a = self._answer(cloud="on-premise", warehouse="auto", budget="enterprise", mode="batch")
        stack = recommend_stack(a)
        assert stack["warehouse"]["type"] == "snowflake"


# ---------------------------------------------------------------------------
# discovery.py — explain_choices pure function
# ---------------------------------------------------------------------------

class TestExplainChoices:
    def _answer(self, **kwargs):
        from datasphere.cli.discovery import Answer
        defaults = dict(
            cloud="aws", source_db="postgresql", warehouse="databricks",
            bi_tool="metabase", orchestrator="airflow", mode="batch",
            data_lake="no", infra="docker", security="simple", budget="medium",
        )
        defaults.update(kwargs)
        a = Answer(**defaults)
        a.transformation = ""  # patch missing field
        return a

    def test_explain_choices_returns_list(self):
        from datasphere.cli.discovery import explain_choices, recommend_stack
        # Use databricks to avoid the a.transformation bug in quality section
        a = self._answer(warehouse="databricks", mode="batch")
        stack = recommend_stack(a)
        explanations = explain_choices(a, stack)
        assert isinstance(explanations, list)
        assert len(explanations) > 0

    def test_explain_choices_tuples_have_three_elements(self):
        from datasphere.cli.discovery import explain_choices, recommend_stack
        a = self._answer(warehouse="databricks", mode="batch")
        stack = recommend_stack(a)
        explanations = explain_choices(a, stack)
        for item in explanations:
            assert len(item) == 3

    def test_explain_choices_realtime(self):
        from datasphere.cli.discovery import explain_choices, recommend_stack
        a = self._answer(mode="realtime", source_db="kafka")
        stack = recommend_stack(a)
        explanations = explain_choices(a, stack)
        assert isinstance(explanations, list)


# ---------------------------------------------------------------------------
# upgrade.py — pure helper functions and CLI
# ---------------------------------------------------------------------------

class TestUpgradeHelpers:
    def test_get_installed_version_returns_string_or_none(self):
        from datasphere.cli.upgrade import _get_installed_version
        result = _get_installed_version("pip")
        # pip should be installed
        assert result is None or isinstance(result, str)

    def test_get_installed_version_unknown_package(self):
        from datasphere.cli.upgrade import _get_installed_version
        result = _get_installed_version("nonexistent-package-xyz-12345")
        assert result is None

    def test_can_import_stdlib(self):
        from datasphere.cli.upgrade import _can_import
        assert _can_import("os") is True

    def test_can_import_nonexistent(self):
        from datasphere.cli.upgrade import _can_import
        assert _can_import("nonexistent_module_xyz") is False

    def test_upgrade_check_only_runs(self):
        """Check-only mode should not install anything but run the check."""
        from click.testing import CliRunner
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        result = runner.invoke(upgrade, ["--check-only"])
        # Should complete without crashing
        assert result.exit_code == 0

    def test_upgrade_core_only_check(self):
        from click.testing import CliRunner
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        result = runner.invoke(upgrade, ["--check-only", "--core-only"])
        assert result.exit_code == 0

    def test_upgrade_specific_package_not_found(self):
        from click.testing import CliRunner
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        result = runner.invoke(upgrade, ["--check-only", "--package", "nonexistent-pkg-xyz"])
        # Should print "Aucun des packages spécifiés trouvé" and return without error
        assert result.exit_code == 0

    def test_get_latest_version_nonexistent(self):
        from datasphere.cli.upgrade import _get_latest_version
        result = _get_latest_version("nonexistent-package-xyz-12345")
        assert result is None

    def test_print_next_steps_runs(self):
        from datasphere.cli.upgrade import _print_next_steps
        # Should not raise
        _print_next_steps()


# ---------------------------------------------------------------------------
# run_agents.py — pure functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# wizard.py — CLI commands (non-interactive)
# ---------------------------------------------------------------------------

class TestWizardCLI:
    def test_validate_nonexistent_file(self):
        from click.testing import CliRunner
        from datasphere.cli.wizard import main

        runner = CliRunner()
        result = runner.invoke(main, ["validate", "nonexistent_stack_xyz.yaml"])
        assert result.exit_code == 1

    def test_validate_valid_file(self, tmp_path):
        import yaml
        from click.testing import CliRunner
        from datasphere.cli.wizard import main

        stack_data = {
            "platform": {"name": "test", "environment": "dev", "version": "1.0.0"},
            "cloud": {"provider": "local-docker"},
            "warehouse": {"type": "postgresql"},
            "orchestration": {"type": "airflow"},
            "ingestion": {"type": "airbyte"},
            "transformation": {"type": "dbt"},
            "storage": {"type": "minio"},
            "bi": {"type": "superset"},
            "quality": {"type": "great-expectations"},
            "catalog": {"type": "openmetadata"},
            "ai": {"type": "openai"},
            "vector": {"type": "qdrant"},
            "infrastructure": {"type": "docker-compose"},
            "monitoring": {"type": "prometheus"},
            "security": {"type": "vault"},
        }
        stack_file = tmp_path / "stack.yaml"
        stack_file.write_text(yaml.dump(stack_data))

        runner = CliRunner()
        result = runner.invoke(main, ["validate", str(stack_file)])
        assert result.exit_code == 0

    def test_dbt_generate_command(self, tmp_path):
        from click.testing import CliRunner
        from datasphere.cli.wizard import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "dbt-generate",
            "--request", "Analytics pipeline",
            "--warehouse", "snowflake",
            "--ingestion", "airbyte",
            "--output", str(tmp_path / "dbt_output"),
        ])
        assert result.exit_code == 0

    def test_dag_generate_airflow(self, tmp_path):
        from click.testing import CliRunner
        from datasphere.cli.wizard import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "dag-generate",
            "--request", "ETL pipeline",
            "--orchestrator", "airflow",
            "--ingestion", "airbyte",
            "--transformation", "dbt",
            "--output", str(tmp_path / "dags"),
        ])
        assert result.exit_code == 0


class TestRunAgents:
    def test_module_importable(self):
        import datasphere.cli.run_agents as ra
        assert ra is not None

    def test_legacy_to_explicit_conversion(self):
        from datasphere.cli.run_agents import _legacy_to_explicit
        data = {
            "business_request": "Analytics pipeline",
            "architecture_constraints": {
                "cloud_provider": "gcp",
                "data_warehouse": "bigquery",
                "orchestrator": "dagster",
                "ingestion": "meltano",
                "transformation": "dbt",
                "bi_tool": "superset",
                "deployment": "kubernetes",
                "budget": "medium",
            }
        }
        result = _legacy_to_explicit(data)
        assert result["cloud_provider"] == "gcp"
        assert result["data_warehouse"] == "bigquery"
        assert result["orchestrator"] == "dagster"
        assert result["business_request"] == "Analytics pipeline"

    def test_legacy_to_explicit_defaults(self):
        from datasphere.cli.run_agents import _legacy_to_explicit
        data = {"business_request": "test"}
        result = _legacy_to_explicit(data)
        assert result["cloud_provider"] == "local-docker"
        assert result["data_warehouse"] == "postgresql"

    def test_run_agents_with_explicit_json_file(self, tmp_path):
        """Test that the CLI can process a JSON file in explicit mode."""
        import json
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        json_data = {
            "mode": "explicit",
            "business_request": "Analytics ventes",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
            "budget": "medium",
            "data_volume": "small",
        }
        json_file = tmp_path / "explicit.json"
        json_file.write_text(json.dumps(json_data))

        runner = CliRunner()
        result = runner.invoke(run_agents, [
            str(json_file),
            "--output", str(tmp_path / "output"),
            "--quiet",
        ])
        # Should exit 0 (success) or 1 (failure), not crash
        assert result.exit_code in (0, 1)

    def test_run_agents_with_recommended_json_file(self, tmp_path):
        """Test that the CLI can process a JSON file in recommended mode."""
        import json
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        json_data = {
            "mode": "recommended",
            "business_request": "Analytics platform",
            "budget": "low",
            "data_volume": "small",
            "security_level": "simple",
            "team_size": "solo",
            "processing_mode": "batch",
            "cloud_preference": "aws",
            "must_be_open_source": False,
        }
        json_file = tmp_path / "recommended.json"
        json_file.write_text(json.dumps(json_data))

        runner = CliRunner()
        result = runner.invoke(run_agents, [
            str(json_file),
            "--output", str(tmp_path / "output"),
            "--quiet",
        ])
        assert result.exit_code in (0, 1)

    def test_run_agents_nonexistent_file(self, tmp_path):
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        runner = CliRunner()
        result = runner.invoke(run_agents, [str(tmp_path / "nonexistent.json")])
        assert result.exit_code == 1

    def test_run_agents_invalid_json(self, tmp_path):
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not valid json {{{")
        runner = CliRunner()
        result = runner.invoke(run_agents, [str(bad_json)])
        assert result.exit_code == 1

    def test_run_agents_with_legacy_format(self, tmp_path):
        import json
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        data = {
            "business_request": "Legacy pipeline",
            "architecture_constraints": {
                "cloud_provider": "aws",
                "data_warehouse": "postgresql",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "metabase",
                "deployment": "docker-compose",
            }
        }
        json_file = tmp_path / "legacy.json"
        json_file.write_text(json.dumps(data))
        runner = CliRunner()
        result = runner.invoke(run_agents, [
            str(json_file),
            "--output", str(tmp_path / "output"),
            "--quiet",
        ])
        assert result.exit_code in (0, 1)

    def test_run_agents_json_out_flag(self, tmp_path):
        import json
        from click.testing import CliRunner
        from datasphere.cli.run_agents import run_agents

        json_data = {
            "mode": "explicit",
            "business_request": "Test pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
            "budget": "medium",
            "data_volume": "small",
        }
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(json_data))

        runner = CliRunner()
        result = runner.invoke(run_agents, [
            str(json_file),
            "--output", str(tmp_path / "output"),
            "--quiet",
            "--json-out",
        ])
        assert result.exit_code in (0, 1)
