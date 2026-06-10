"""
Tests E2E — couvrent le pipeline complet de bout en bout :
  BusinessRequest → 6 agents → OrchestratorOutput + artifacts générés
"""
from __future__ import annotations
import pytest
import tempfile
from pathlib import Path

from datasphere.models.request import ArchitectureConstraints
from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.agents.mode_router import run_explicit, run_recommended


def _aws_stack(**kwargs) -> ExplicitStack:
    defaults = dict(
        business_request="Pipeline e-commerce : ventes, stocks, clients",
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="superset",
        deployment="kubernetes",
        data_lake="s3",
        catalog="openmetadata",
        quality="great-expectations",
        security=["RBAC"],
        budget="medium",
        data_volume="medium",
        processing_mode="batch",
    )
    defaults.update(kwargs)
    return ExplicitStack(**defaults)


# ---------------------------------------------------------------------------
# Mode 1 — explicit stack E2E
# ---------------------------------------------------------------------------

class TestExplicitStackE2E:

    def test_full_pipeline_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
        assert result.success is True
        assert not result.errors

    def test_all_agents_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
        assert result.stack_advisor is not None
        assert result.cloud_architect is not None
        assert result.infrastructure is not None
        assert result.cost_optimization is not None
        assert result.security_compliance is not None
        assert result.deployment is not None

    def test_cost_estimate_is_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
        cost = result.cost_optimization
        assert cost is not None
        assert cost.total_monthly_usd > 0
        assert cost.total_yearly_usd == pytest.approx(cost.total_monthly_usd * 12, rel=0.01)

    def test_stack_advisor_validates_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
        advisor = result.stack_advisor
        assert advisor is not None
        # validated_stack uses short keys: warehouse, orchestration, ingestion…
        vs = advisor.validated_stack
        assert vs.get("warehouse") == "snowflake" or vs.get("data_warehouse") == "snowflake"
        orch = vs.get("orchestration") or vs.get("orchestrator") or ""
        assert "airflow" in orch

    def test_deployment_has_pipeline_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
        dep = result.deployment
        assert dep is not None
        assert len(dep.pipeline_stages) > 0

    def test_security_has_rbac(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(security=["RBAC"]), output_dir=tmp, verbose=False)
        sec = result.security_compliance
        assert sec is not None
        assert sec.success

    def test_artifacts_written_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_explicit(_aws_stack(), output_dir=tmp, verbose=False)
            written_files = list(Path(tmp).rglob("*"))
        assert len(written_files) > 0

    def test_gcp_bigquery_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(cloud_provider="gcp", data_warehouse="bigquery", data_lake="gcs")
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success
        ca = result.cloud_architect
        assert ca is not None
        assert ca.provider == "gcp"

    def test_azure_synapse_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(cloud_provider="azure", data_warehouse="azure-synapse", data_lake="adls")
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success

    def test_enterprise_budget_has_higher_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            r_med = run_explicit(_aws_stack(budget="medium"), output_dir=tmp, verbose=False)
        with tempfile.TemporaryDirectory() as tmp:
            r_ent = run_explicit(_aws_stack(budget="enterprise"), output_dir=tmp, verbose=False)
        assert r_ent.cost_optimization.total_monthly_usd >= r_med.cost_optimization.total_monthly_usd

    def test_realtime_mode_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(
                orchestrator="dagster",
                ingestion="kafka-connect",
                processing_mode="realtime",
            )
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success

    def test_dagster_orchestrator_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(orchestrator="dagster")
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success
        vs = result.stack_advisor.validated_stack
        orch = vs.get("orchestration") or vs.get("orchestrator") or ""
        assert "dagster" in orch

    def test_prefect_orchestrator_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(orchestrator="prefect")
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success

    def test_low_budget_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(
                budget="low",
                data_warehouse="duckdb",
                cloud_provider="local-docker",
                deployment="docker-compose",
                data_lake="minio",
            )
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        assert result.success
        assert result.cost_optimization.total_monthly_usd < 500

    def test_result_summary_contains_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            stack = _aws_stack(business_request="Analyse des ventes retail")
            result = run_explicit(stack, output_dir=tmp, verbose=False)
        summary = result.summary()
        assert "Analyse des ventes retail" in summary


# ---------------------------------------------------------------------------
# Mode 2 — recommended stack E2E
# ---------------------------------------------------------------------------

class TestRecommendedStackE2E:

    def _ctx(self, **kwargs) -> RecommendationContext:
        defaults = dict(
            business_request="Plateforme analytics pour startup SaaS",
            budget="medium",
            data_volume="medium",
            security_level="rbac",
            team_size="small",
            processing_mode="batch",
            cloud_preference="aws",
            must_be_open_source=False,
        )
        defaults.update(kwargs)
        return RecommendationContext(**defaults)

    def test_recommended_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_recommended(self._ctx(), output_dir=tmp, verbose=False)
        assert result.success

    def test_recommended_selects_warehouse(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_recommended(self._ctx(), output_dir=tmp, verbose=False)
        assert result.stack_advisor is not None
        vs = result.stack_advisor.validated_stack
        wh = vs.get("warehouse") or vs.get("data_warehouse")
        assert wh is not None

    def test_open_source_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_recommended(
                self._ctx(must_be_open_source=True, cloud_preference="none"),
                output_dir=tmp, verbose=False,
            )
        assert result.success
        vs = result.stack_advisor.validated_stack
        wh = vs.get("warehouse") or vs.get("data_warehouse") or ""
        assert wh not in ("snowflake", "bigquery", "azure-synapse"), \
            f"Expected open-source warehouse, got {wh}"

    def test_enterprise_recommended_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_recommended(
                self._ctx(budget="enterprise", data_volume="xlarge", team_size="large"),
                output_dir=tmp, verbose=False,
            )
        assert result.success
        assert result.cost_optimization.total_monthly_usd > 0


# ---------------------------------------------------------------------------
# Full API E2E (via TestClient)
# ---------------------------------------------------------------------------

class TestAPIE2E:

    def setup_method(self):
        if "DATASPHERE_API_KEY" in os.environ:
            del os.environ["DATASPHERE_API_KEY"]
        from datasphere.api.app import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)

    def test_full_generate_sync_explicit(self):
        payload = {
            "mode": "explicit",
            "business_request": "API E2E test — retail pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
            "budget": "medium",
        }
        r = self.client.post("/generate/sync", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "stack_advisor" in data
        assert "cost_optimization" in data

    def test_dbt_generate_e2e(self):
        r = self.client.post("/dbt/generate", json={
            "business_request": "E2E dbt pipeline",
            "data_warehouse": "bigquery",
            "cloud_provider": "gcp",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
            "security": ["RBAC"],
            "budget": "medium",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["file_count"] >= 10
        assert "dbt_project.yml" in data["files"]
        assert "profiles.yml" in data["files"]

    def test_dagster_generate_e2e(self):
        r = self.client.post("/dagster/generate", json={
            "business_request": "E2E Dagster pipeline",
            "data_warehouse": "snowflake",
            "cloud_provider": "aws",
            "orchestrator": "dagster",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
            "security": ["RBAC"],
            "budget": "medium",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["file_count"] >= 8
        assert "workspace.yaml" in data["files"]

    def test_prefect_generate_e2e(self):
        r = self.client.post("/prefect/generate", json={
            "business_request": "E2E Prefect pipeline",
            "data_warehouse": "snowflake",
            "cloud_provider": "aws",
            "orchestrator": "prefect",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "kubernetes",
            "security": ["RBAC"],
            "budget": "low",
        })
        assert r.status_code == 200
        data = r.json()
        assert "prefect.yaml" in data["files"]
        assert "deployments.yaml" in data["files"]

    def test_async_generate_and_poll(self):
        import time
        payload = {
            "mode": "explicit",
            "business_request": "Async E2E test",
            "cloud_provider": "aws",
            "data_warehouse": "postgresql",
            "orchestrator": "airflow",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
            "budget": "low",
        }
        # Launch async job
        r = self.client.post("/generate", json=payload)
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        assert job_id

        # Poll until complete or timeout
        for _ in range(30):
            status_r = self.client.get(f"/jobs/{job_id}")
            assert status_r.status_code == 200
            status = status_r.json()["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(0.2)

        final = self.client.get(f"/jobs/{job_id}").json()
        assert final["status"] == "completed", f"Expected completed, got {final['status']}: {final.get('error')}"


import os
