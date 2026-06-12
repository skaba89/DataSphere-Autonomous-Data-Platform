"""Tests for predefined stack templates."""
import pytest
from fastapi.testclient import TestClient

from datasphere.generators.templates import StackTemplate, TemplateRegistry, template_registry
from datasphere.api.app import create_app

app = create_app()
client = TestClient(app, headers={"Authorization": "Bearer test"})


class TestTemplateRegistry:
    def test_template_registry_has_templates(self):
        templates = template_registry.list_all()
        assert len(templates) >= 10

    def test_all_templates_have_required_fields(self):
        for t in template_registry.list_all():
            assert t.id, f"Template missing id: {t}"
            assert t.name, f"Template missing name: {t.id}"
            assert t.description, f"Template missing description: {t.id}"
            assert isinstance(t.constraints, dict), f"Template {t.id} constraints must be dict"
            assert len(t.constraints) > 0, f"Template {t.id} constraints must not be empty"

    def test_startup_analytics_template_exists(self):
        t = template_registry.get("startup-analytics")
        assert t is not None
        assert t.name == "Startup Analytics"
        assert t.category == "startup"
        assert t.estimated_monthly_usd == 200

    def test_modern_data_stack_aws_exists(self):
        t = template_registry.get("modern-data-stack-aws")
        assert t is not None
        assert t.category == "analytics"
        assert t.estimated_monthly_usd == 2500

    def test_get_template_by_id(self):
        t = template_registry.get("local-dev")
        assert t is not None
        assert t.id == "local-dev"
        assert t.estimated_monthly_usd == 0

    def test_get_nonexistent_template_returns_none(self):
        t = template_registry.get("does-not-exist-xyz")
        assert t is None

    def test_list_by_category_startup(self):
        startups = template_registry.list_by_category("startup")
        assert len(startups) >= 2
        assert all(t.category == "startup" for t in startups)

    def test_list_by_category_enterprise(self):
        enterprise = template_registry.list_by_category("enterprise")
        assert len(enterprise) >= 2
        assert all(t.category == "enterprise" for t in enterprise)

    def test_search_by_keyword(self):
        results = template_registry.search("snowflake")
        assert len(results) >= 1
        ids = [t.id for t in results]
        assert "modern-data-stack-aws" in ids

    def test_search_by_tag(self):
        results = template_registry.search("streaming")
        assert len(results) >= 1


class TestTemplatesAPI:
    def test_api_list_templates_200(self):
        r = client.get("/templates")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert data["count"] >= 10
        assert "templates" in data
        assert len(data["templates"]) >= 10

    def test_api_list_templates_filtered_by_category(self):
        r = client.get("/templates?category=startup")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1
        for t in data["templates"]:
            assert t["category"] == "startup"

    def test_api_get_template_200(self):
        r = client.get("/templates/startup-analytics")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "startup-analytics"
        assert "constraints" in data
        assert "pros" in data
        assert "cons" in data
        assert "use_cases" in data

    def test_api_get_template_404(self):
        r = client.get("/templates/nonexistent-template-xyz")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_api_generate_from_template_returns_job_id(self):
        r = client.post("/generate/from-template", json={
            "template_id": "startup-analytics",
            "business_request": "Build a data pipeline for SaaS metrics tracking",
        })
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "startup-analytics" in data["message"]

    def test_api_generate_from_template_with_overrides(self):
        r = client.post("/generate/from-template", json={
            "template_id": "modern-data-stack-aws",
            "business_request": "Analytics platform with custom BI tool",
            "overrides": {"bi_tool": "superset"},
        })
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_api_generate_from_template_invalid_template_404(self):
        r = client.post("/generate/from-template", json={
            "template_id": "nonexistent-xyz",
            "business_request": "Some business request",
        })
        assert r.status_code == 404

    def test_api_list_templates_filtered_by_budget(self):
        r = client.get("/templates?budget=low")
        assert r.status_code == 200
        data = r.json()
        for t in data["templates"]:
            assert t["stack"].get("budget") == "low"
