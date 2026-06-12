"""Tests de l'API FastAPI DataSphere."""
import json
import pytest
from fastapi.testclient import TestClient
from datasphere.api.app import create_app

app = create_app()
client = TestClient(app)


class TestHealth:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_lists_endpoints(self):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "endpoints" in data
        assert any("/generate" in e for e in data["endpoints"])


class TestSupportedStacks:
    def test_supported_stacks_returns_categories(self):
        r = client.get("/stacks/supported")
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data
        cats = data["categories"]
        assert "warehouse" in cats
        assert "orchestration" in cats

    def test_adapters_endpoint_returns_registry(self):
        r = client.get("/stacks/adapters")
        assert r.status_code == 200
        data = r.json()
        assert "adapter_count" in data
        assert data["adapter_count"] >= 30
        assert "warehouse" in data["adapters"]
        assert "postgresql" in data["adapters"]["warehouse"]


class TestProposals:
    def test_proposals_returns_2_or_3(self):
        r = client.post("/proposals", json={
            "cloud_provider": "aws",
            "budget": "enterprise",
            "data_volume": "large",
        })
        assert r.status_code == 200
        data = r.json()
        assert 2 <= data["count"] <= 3

    def test_proposals_have_required_fields(self):
        r = client.post("/proposals", json={
            "cloud_provider": "gcp",
            "budget": "medium",
        })
        assert r.status_code == 200
        for p in r.json()["proposals"]:
            assert "id" in p
            assert "name" in p
            assert "stack" in p
            assert "estimated_monthly_usd" in p
            assert "pros" in p

    def test_low_budget_no_snowflake(self):
        r = client.post("/proposals", json={
            "cloud_provider": "local-docker",
            "budget": "low",
            "deployment": "docker-compose",
        })
        assert r.status_code == 200
        for p in r.json()["proposals"]:
            assert p["stack"]["warehouse"] != "snowflake"


class TestDbtGenerate:
    def test_generates_files(self):
        r = client.post("/dbt/generate", json={
            "business_request": "Analyse les ventes",
            "data_warehouse": "snowflake",
            "ingestion": "airbyte",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["file_count"] >= 10
        assert "dbt_project.yml" in data["files"]
        assert "profiles.yml" in data["files"]

    def test_generates_staging_models(self):
        r = client.post("/dbt/generate", json={
            "business_request": "Tableau de bord KPIs",
            "data_warehouse": "postgresql",
            "ingestion": "meltano",
        })
        assert r.status_code == 200
        files = r.json()["files"]
        assert any("stg_orders" in k for k in files)

    def test_generates_mart_models(self):
        r = client.post("/dbt/generate", json={
            "business_request": "Analyse clients",
            "data_warehouse": "bigquery",
        })
        assert r.status_code == 200
        files = r.json()["files"]
        assert any("fct_orders" in k for k in files)
        assert any("dim_customers" in k for k in files)

    def test_project_name_in_response(self):
        r = client.post("/dbt/generate", json={
            "business_request": "Analyse des ventes",
            "data_warehouse": "snowflake",
        })
        assert r.status_code == 200
        assert "project_name" in r.json()
        assert r.json()["warehouse"] == "snowflake"


class TestAirflowDagGenerate:
    def test_generates_two_dags(self):
        r = client.post("/dags/airflow/generate", json={
            "business_request": "Pipeline ventes quotidien",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "data_warehouse": "snowflake",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["dag_count"] == 2

    def test_pipeline_dag_content(self):
        r = client.post("/dags/airflow/generate", json={
            "business_request": "Test DAG",
            "ingestion": "meltano",
            "transformation": "dbt",
            "data_warehouse": "postgresql",
        })
        assert r.status_code == 200
        files = r.json()["files"]
        pipeline = next(v for k, v in files.items() if "pipeline" in k)
        assert "with DAG(" in pipeline
        assert "meltano run" in pipeline

    def test_quality_dag_has_sensor(self):
        r = client.post("/dags/airflow/generate", json={
            "business_request": "Test DAG",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "quality": "soda-core",
        })
        assert r.status_code == 200
        files = r.json()["files"]
        quality = next(v for k, v in files.items() if "quality" in k)
        assert "ExternalTaskSensor" in quality


class TestGenerateSync:
    def test_explicit_mode_sync(self):
        r = client.post("/generate/sync", json={
            "mode": "explicit",
            "business_request": "Test API pipeline",
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "kubernetes",
            "security": ["RBAC"],
            "budget": "enterprise",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "stack_advisor" in data
        assert "cost_optimization" in data
        assert data["cost_optimization"]["total_monthly_usd"] > 0

    def test_recommended_mode_sync(self):
        r = client.post("/generate/sync", json={
            "mode": "recommended",
            "business_request": "Tableau de bord analytique",
            "budget": "medium",
            "data_volume": "medium",
            "security_level": "rbac",
            "team_size": "small",
            "cloud_preference": "gcp",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

    def test_missing_business_request_returns_422(self):
        r = client.post("/generate/sync", json={
            "mode": "explicit",
            "cloud_provider": "aws",
        })
        assert r.status_code == 422

    def test_invalid_mode_returns_422(self):
        r = client.post("/generate/sync", json={
            "mode": "unknown",
            "business_request": "Test",
        })
        assert r.status_code == 422


class TestAsyncGenerate:
    def test_async_generate_returns_job_id(self):
        r = client.post("/generate", json={
            "mode": "explicit",
            "business_request": "Async test",
            "cloud_provider": "aws",
            "data_warehouse": "postgresql",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "superset",
            "deployment": "docker-compose",
            "budget": "low",
        })
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_job_status_endpoint(self):
        r = client.post("/generate", json={
            "mode": "explicit",
            "business_request": "Job status test",
            "cloud_provider": "local-docker",
            "data_warehouse": "postgresql",
            "orchestrator": "dagster",
            "ingestion": "meltano",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "docker-compose",
            "budget": "low",
        })
        job_id = r.json()["job_id"]
        r2 = client.get(f"/jobs/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["job_id"] == job_id

    def test_unknown_job_returns_404(self):
        r = client.get("/jobs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_list_jobs(self):
        r = client.get("/jobs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestDownloadEndpoint:
    def test_download_completed_job_returns_zip(self):
        import io, zipfile, uuid
        from datasphere.api.job_store import job_store

        job_id = str(uuid.uuid4())
        fake_result = {
            "success": True,
            "errors": [],
            "request_summary": "test",
            "artifacts_path": "",
            "stack_advisor": {
                "success": True,
                "warnings": [],
                "errors": [],
                "artifact_keys": ["stack.yml"],
                "validated_stack": {"warehouse": "snowflake", "orchestrator": "airflow"},
            },
            "cost_optimization": {
                "success": True,
                "warnings": [],
                "errors": [],
                "artifact_keys": [],
                "total_monthly_usd": 1234,
                "total_yearly_usd": 14808,
                "optimizations": ["Use reserved instances"],
            },
        }
        job_store.create(job_id, status="pending")
        job_store.update(job_id, status="completed", result=fake_result)

        r = client.get(f"/jobs/{job_id}/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert f"datasphere-{job_id[:8]}.zip" in r.headers.get("content-disposition", "")

        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "stack_report.md" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["job_id"] == job_id
            assert manifest["stack_summary"]["warehouse"] == "snowflake"

    def test_download_nonexistent_job_returns_404(self):
        r = client.get("/jobs/00000000-dead-beef-0000-000000000000/download")
        assert r.status_code == 404

    def test_download_pending_job_returns_404(self):
        import uuid
        from datasphere.api.job_store import job_store

        job_id = str(uuid.uuid4())
        job_store.create(job_id, status="pending")
        r = client.get(f"/jobs/{job_id}/download")
        assert r.status_code == 404
