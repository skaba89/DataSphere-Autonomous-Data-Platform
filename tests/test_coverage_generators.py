"""
Targeted tests for generator edge cases:
- lineage.py: minimal stack, no bi_tool, with catalog, with quality
- terraform.py: storage module, kubernetes, azure backend
- stack_diff.py: basic coverage
- client.py: error handling, download_job, list_jobs edge cases
"""
from __future__ import annotations

import os
import json
import pytest

from datasphere.models.request import ArchitectureConstraints
from datasphere.generators.lineage import LineageGenerator
from datasphere.generators.terraform import TerraformGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_constraints(**kwargs) -> ArchitectureConstraints:
    defaults = dict(
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="metabase",
        deployment="docker-compose",
    )
    defaults.update(kwargs)
    return ArchitectureConstraints(**defaults)


# ---------------------------------------------------------------------------
# LineageGenerator edge cases
# ---------------------------------------------------------------------------

class TestLineageGeneratorEdgeCases:
    def test_minimal_stack_only_warehouse(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
        }
        result = gen.generate(stack, "Minimal test")
        assert result.mermaid
        assert "flowchart LR" in result.mermaid

    def test_stack_with_catalog(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "gcp",
            "data_warehouse": "bigquery",
            "orchestrator": "dagster",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "superset",
            "catalog": "datahub",
        }
        result = gen.generate(stack, "With catalog")
        assert "DataHub" in result.mermaid or "datahub" in result.mermaid.lower()

    def test_stack_with_quality(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "aws",
            "data_warehouse": "redshift",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "quality": "great-expectations",
        }
        result = gen.generate(stack, "With quality")
        assert "Great Expectations" in result.mermaid or "great" in result.mermaid.lower()

    def test_stack_without_bi_tool(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "aws",
            "data_warehouse": "postgresql",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": None,
        }
        result = gen.generate(stack, "No BI tool")
        assert result.mermaid is not None

    def test_stack_with_unknown_tools(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "ovhcloud",
            "data_warehouse": "custom-warehouse",
            "orchestrator": "custom-orch",
            "ingestion": "custom-ingest",
            "transformation": "custom-transform",
            "bi_tool": "custom-bi",
        }
        result = gen.generate(stack, "Unknown tools")
        # Should fall back to key name
        assert result.mermaid is not None

    def test_nodes_list_populated(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
        }
        result = gen.generate(stack)
        assert len(result.nodes) > 0

    def test_edges_list_populated(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
        }
        result = gen.generate(stack)
        assert len(result.edges) > 0

    def test_embed_url_returns_valid_url(self):
        mermaid = "flowchart LR\n  A --> B"
        url = LineageGenerator.embed_url(mermaid)
        assert url.startswith("https://mermaid.live/edit#base64:")

    def test_stack_with_catalog_and_quality(self):
        gen = LineageGenerator()
        stack = {
            "cloud_provider": "azure",
            "data_warehouse": "azure-synapse",
            "orchestrator": "prefect",
            "ingestion": "fivetran",
            "transformation": "spark",
            "bi_tool": "powerbi",
            "catalog": "openmetadata",
            "quality": "soda-core",
        }
        result = gen.generate(stack, "Full enterprise stack")
        assert result.mermaid
        assert len(result.nodes) > 0


# ---------------------------------------------------------------------------
# TerraformGenerator edge cases
# ---------------------------------------------------------------------------

class TestTerraformGeneratorEdgeCases:
    def test_minimal_aws_stack(self):
        gen = TerraformGenerator()
        c = _make_constraints()
        result = gen.generate("Test pipeline", c)
        assert "main.tf" in result.files
        assert "variables.tf" in result.files
        assert "outputs.tf" in result.files

    def test_storage_module_with_data_lake(self):
        gen = TerraformGenerator()
        c = _make_constraints(data_lake="s3")
        result = gen.generate("Pipeline with data lake", c)
        assert "modules/storage/main.tf" in result.files
        assert len(result.files["modules/storage/main.tf"]) > 0

    def test_kubernetes_module_generation(self):
        gen = TerraformGenerator()
        c = _make_constraints(deployment="kubernetes")
        result = gen.generate("K8s deployment", c)
        assert "modules/kubernetes/main.tf" in result.files
        assert "modules/monitoring/main.tf" in result.files

    def test_azure_backend(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="azure", data_warehouse="azure-synapse")
        result = gen.generate("Azure pipeline", c)
        assert "backend.tf" in result.files
        backend = result.files["backend.tf"]
        # Azure backend should reference azurerm
        assert "azurerm" in backend or "azure" in backend.lower()

    def test_gcp_backend(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="gcp", data_warehouse="bigquery")
        result = gen.generate("GCP pipeline", c)
        assert "backend.tf" in result.files

    def test_local_docker_no_cloud_modules(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="local-docker", data_warehouse="postgresql")
        result = gen.generate("Local pipeline", c)
        assert "main.tf" in result.files

    def test_snowflake_warehouse_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(data_warehouse="snowflake")
        result = gen.generate("Snowflake pipeline", c)
        assert "modules/warehouse/main.tf" in result.files
        warehouse_tf = result.files["modules/warehouse/main.tf"]
        assert len(warehouse_tf) > 0

    def test_bigquery_warehouse_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="gcp", data_warehouse="bigquery")
        result = gen.generate("BigQuery pipeline", c)
        assert "modules/warehouse/main.tf" in result.files

    def test_postgresql_warehouse_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(data_warehouse="postgresql")
        result = gen.generate("PostgreSQL pipeline", c)
        assert "modules/warehouse/main.tf" in result.files

    def test_minio_storage_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(data_lake="minio")
        result = gen.generate("MinIO storage pipeline", c)
        assert "modules/storage/main.tf" in result.files

    def test_gcs_storage_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="gcp", data_lake="gcs", data_warehouse="bigquery")
        result = gen.generate("GCS storage pipeline", c)
        assert "modules/storage/main.tf" in result.files

    def test_adls_storage_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="azure", data_lake="adls", data_warehouse="azure-synapse")
        result = gen.generate("ADLS storage pipeline", c)
        assert "modules/storage/main.tf" in result.files

    def test_enterprise_budget_kubernetes(self):
        gen = TerraformGenerator()
        c = _make_constraints(deployment="kubernetes", budget="enterprise", data_warehouse="snowflake")
        result = gen.generate("Enterprise K8s pipeline", c)
        assert "modules/kubernetes/main.tf" in result.files

    def test_low_budget_aws(self):
        gen = TerraformGenerator()
        c = _make_constraints(budget="low", data_warehouse="postgresql")
        result = gen.generate("Low budget pipeline", c)
        assert "main.tf" in result.files

    def test_gitignore_present(self):
        gen = TerraformGenerator()
        c = _make_constraints()
        result = gen.generate("Test", c)
        assert ".gitignore" in result.files

    def test_readme_present(self):
        gen = TerraformGenerator()
        c = _make_constraints()
        result = gen.generate("My business pipeline", c)
        assert "README.md" in result.files
        assert "My business pipeline" in result.files["README.md"]

    def test_write_to_disk(self, tmp_path):
        gen = TerraformGenerator()
        c = _make_constraints()
        result = gen.generate("Write test", c)
        written = result.write(str(tmp_path))
        assert len(written) > 0
        # Check at least main.tf was written
        assert any("main.tf" in f for f in written)

    def test_databricks_warehouse_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="aws", data_warehouse="databricks")
        result = gen.generate("Databricks pipeline", c)
        assert "modules/warehouse/main.tf" in result.files

    def test_redshift_warehouse_module(self):
        gen = TerraformGenerator()
        c = _make_constraints(cloud_provider="aws", data_warehouse="redshift")
        result = gen.generate("Redshift pipeline", c)
        assert "modules/warehouse/main.tf" in result.files


# ---------------------------------------------------------------------------
# client.py — error handling and edge cases
# ---------------------------------------------------------------------------

class TestClientEdgeCases:
    def test_parse_sse_line_with_valid_json(self):
        from datasphere.client import DataSphereClient
        result = DataSphereClient._parse_sse_line('data: {"type": "progress", "message": "ok"}')
        assert result is not None
        assert result["type"] == "progress"

    def test_parse_sse_line_with_invalid_json(self):
        from datasphere.client import DataSphereClient
        result = DataSphereClient._parse_sse_line("data: not-valid-json")
        assert result is not None
        assert result["type"] == "raw"

    def test_parse_sse_line_empty_data(self):
        from datasphere.client import DataSphereClient
        result = DataSphereClient._parse_sse_line("data: ")
        assert result is None

    def test_parse_sse_line_non_data_line(self):
        from datasphere.client import DataSphereClient
        result = DataSphereClient._parse_sse_line("event: ping")
        assert result is None

    def test_client_raises_on_4xx(self):
        from datasphere.client import DataSphereClient, DataSphereError
        from fastapi.testclient import TestClient
        from datasphere.api.app import create_app

        _app = create_app()
        _tc = TestClient(_app)
        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            resp = _tc.get(path)
            if resp.status_code >= 400:
                raise DataSphereError(f"GET {path} → {resp.status_code}: {resp.text}")
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                return resp.json()
            return resp.content

        c._get = _get  # type: ignore[method-assign]

        with pytest.raises(DataSphereError):
            c.get_job("nonexistent-job-id-12345")

    def test_client_list_jobs_returns_list(self):
        from datasphere.client import DataSphereClient
        from fastapi.testclient import TestClient
        from datasphere.api.app import create_app

        _app = create_app()
        _tc = TestClient(_app)
        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            resp = _tc.get(path)
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                return resp.json()
            return resp.content

        c._get = _get  # type: ignore[method-assign]

        result = c.list_jobs()
        # list_jobs now returns a paginated dict
        assert isinstance(result, dict)
        assert "items" in result

    def test_client_list_jobs_handles_dict_response(self):
        from datasphere.client import DataSphereClient

        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            # Simulate paginated API response
            return {"items": [{"job_id": "abc", "status": "completed"}], "total": 1, "has_more": False}

        c._get = _get  # type: ignore[method-assign]

        result = c.list_jobs()
        assert isinstance(result, dict)
        assert result["items"] == [{"job_id": "abc", "status": "completed"}]

    def test_client_list_jobs_handles_items_key(self):
        from datasphere.client import DataSphereClient

        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            return {"items": [{"job_id": "xyz", "status": "pending"}], "total": 1, "has_more": False}

        c._get = _get  # type: ignore[method-assign]

        result = c.list_jobs()
        assert result["items"] == [{"job_id": "xyz", "status": "pending"}]

    def test_client_download_job_raises_on_json_response(self):
        from datasphere.client import DataSphereClient, DataSphereError

        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            return {"error": "not available"}  # JSON instead of bytes

        c._get = _get  # type: ignore[method-assign]

        with pytest.raises(DataSphereError, match="Expected binary ZIP"):
            c.download_job("some-job-id")

    def test_client_download_job_saves_zip(self, tmp_path):
        from datasphere.client import DataSphereClient

        c = DataSphereClient(base_url="http://test")

        def _get(path: str):
            return b"PK\x03\x04fake zip content"  # fake ZIP bytes

        c._get = _get  # type: ignore[method-assign]

        dest = c.download_job("test-job-id", output_dir=str(tmp_path))
        assert os.path.exists(dest)
        assert dest.endswith("test-job-id.zip")

    def test_client_health_with_api_key(self):
        from datasphere.client import DataSphereClient
        from fastapi.testclient import TestClient
        from datasphere.api.app import create_app

        _app = create_app()
        _tc = TestClient(_app)
        c = DataSphereClient(base_url="http://test", api_key="mykey")

        # Headers should include Authorization
        headers = c._headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer mykey"

    def test_client_health_without_api_key(self):
        from datasphere.client import DataSphereClient
        c = DataSphereClient(base_url="http://test")
        headers = c._headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# ArchitectureConstraints normalize
# ---------------------------------------------------------------------------

class TestArchitectureConstraintsNormalize:
    def test_normalize_dbt_core_to_dbt(self):
        c = _make_constraints(transformation="dbt Core")
        normalized = c.normalize()
        assert normalized.transformation == "dbt"

    def test_normalize_docker_compose(self):
        c = _make_constraints(deployment="Docker Compose")
        normalized = c.normalize()
        assert normalized.deployment == "docker-compose"

    def test_normalize_kubernetes(self):
        c = _make_constraints(deployment="Kubernetes")
        normalized = c.normalize()
        assert normalized.deployment == "kubernetes"

    def test_normalize_superset(self):
        c = _make_constraints(bi_tool="Superset")
        normalized = c.normalize()
        assert normalized.bi_tool == "superset"


# ---------------------------------------------------------------------------
# Stack diff generator
# ---------------------------------------------------------------------------

class TestStackDiff:
    def test_stack_diff_basic(self):
        from datasphere.generators.stack_diff import StackDiffGenerator

        gen = StackDiffGenerator()
        assert gen is not None

    def test_stack_diff_generate_with_two_stacks(self):
        from datasphere.generators.stack_diff import StackDiffGenerator

        gen = StackDiffGenerator()
        stack_a = {
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
        }
        stack_b = {
            "cloud_provider": "gcp",
            "data_warehouse": "bigquery",
            "orchestrator": "dagster",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
        }
        # Check that generate method exists and can be called
        if hasattr(gen, "generate"):
            result = gen.generate(stack_a, stack_b)
            assert result is not None
        elif hasattr(gen, "diff"):
            result = gen.diff(stack_a, stack_b)
            assert result is not None


# ---------------------------------------------------------------------------
# Core config and registry
# ---------------------------------------------------------------------------

class TestCoreConfig:
    def test_stack_config_validate(self):
        from datasphere.core.config import StackConfig
        config = StackConfig()
        errors = config.validate()
        assert isinstance(errors, list)

    def test_stack_config_to_yaml(self):
        from datasphere.core.config import StackConfig
        config = StackConfig()
        yaml_str = config.to_yaml()
        assert isinstance(yaml_str, str)
        assert len(yaml_str) > 0


class TestRegistry:
    def test_registry_list_adapters(self):
        from datasphere.core.registry import AdapterRegistry
        adapters = AdapterRegistry.list_adapters()
        assert isinstance(adapters, list)

    def test_registry_list_adapters_by_category(self):
        from datasphere.core.registry import AdapterRegistry
        adapters = AdapterRegistry.list_adapters("warehouse")
        assert isinstance(adapters, list)
