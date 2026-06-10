"""Integration tests for the multi-agent orchestrator."""
import json
import pytest
from pathlib import Path

from datasphere.models.request import BusinessRequest, ArchitectureConstraints
from datasphere.agents.orchestrator import AgentOrchestrator


def make_request(cloud="aws", warehouse="snowflake", orchestrator="airflow",
                 ingestion="airbyte", transformation="dbt Core", data_lake="S3",
                 bi_tool="superset", security=None, budget="enterprise",
                 business="Test pipeline"):
    return BusinessRequest(
        business_request=business,
        architecture_constraints=ArchitectureConstraints(
            cloud_provider=cloud,
            data_warehouse=warehouse,
            orchestrator=orchestrator,
            ingestion=ingestion,
            transformation=transformation,
            data_lake=data_lake,
            bi_tool=bi_tool,
            catalog="openmetadata",
            quality="great-expectations",
            deployment="kubernetes",
            iac="terraform",
            security=security or ["RBAC", "Vault"],
            budget=budget,
        )
    )


class TestStackAdvisor:
    def test_validates_compatible_stack(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent
        req = make_request()
        out = StackAdvisorAgent().run(req)
        assert out.success
        assert "warehouse" in out.validated_stack

    def test_warns_on_xlarge_with_dbt_only(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent
        from datasphere.models.request import ArchitectureConstraints
        req = make_request(warehouse="postgresql", transformation="dbt Core")
        req = BusinessRequest(
            business_request=req.business_request,
            architecture_constraints=ArchitectureConstraints(
                **{**req.architecture_constraints.model_dump(), "data_volume": "xlarge"}
            )
        )
        out = StackAdvisorAgent().run(req)
        assert any("xlarge" in w.lower() for w in out.warnings)

    def test_warns_snowflake_low_budget(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent
        req = make_request(warehouse="snowflake", budget="low")
        out = StackAdvisorAgent().run(req)
        assert any("snowflake" in w.lower() for w in out.warnings)


class TestCloudArchitect:
    def test_aws_services(self):
        from datasphere.agents.cloud_architect import CloudArchitectAgent
        req = make_request(cloud="aws")
        out = CloudArchitectAgent().run(req)
        assert out.provider == "aws"
        assert out.region != ""
        assert len(out.services) > 0

    def test_gcp_recommends_bigquery(self):
        from datasphere.agents.cloud_architect import CloudArchitectAgent
        req = make_request(cloud="gcp", warehouse="postgresql")
        out = CloudArchitectAgent().run(req)
        assert any("BigQuery" in r for r in out.recommendations)

    def test_local_docker(self):
        from datasphere.agents.cloud_architect import CloudArchitectAgent
        req = make_request(cloud="local-docker")
        out = CloudArchitectAgent().run(req)
        assert out.provider == "local-docker"


class TestCostOptimization:
    def test_estimates_non_zero_for_enterprise(self):
        from datasphere.agents.cost_optimization import CostOptimizationAgent
        req = make_request(warehouse="snowflake", budget="enterprise")
        out = CostOptimizationAgent().run(req)
        assert out.total_monthly_usd > 0
        assert out.total_yearly_usd == pytest.approx(out.total_monthly_usd * 12, rel=0.01)

    def test_free_stack_zero_cost(self):
        from datasphere.agents.cost_optimization import CostOptimizationAgent
        req = make_request(
            cloud="local-docker", warehouse="postgresql",
            orchestrator="airflow", ingestion="meltano",
            transformation="dbt Core", data_lake="minio",
            bi_tool="superset", budget="low",
        )
        req.architecture_constraints.deployment = "docker-compose"
        out = CostOptimizationAgent().run(req)
        assert out.total_monthly_usd < 50  # nearly free

    def test_suggests_opensource_alternatives(self):
        from datasphere.agents.cost_optimization import CostOptimizationAgent
        req = make_request(bi_tool="tableau", budget="enterprise")
        out = CostOptimizationAgent().run(req)
        assert any("tableau" in opt.lower() for opt in out.optimizations)


class TestSecurity:
    def test_rls_generated_for_snowflake(self):
        from datasphere.agents.security_compliance import SecurityComplianceAgent
        req = make_request(warehouse="snowflake", security=["RBAC", "RLS", "Vault"])
        out = SecurityComplianceAgent().run(req)
        assert len(out.rls_policies) > 0
        assert any("ROW ACCESS POLICY" in line for line in out.rls_policies)

    def test_healthcare_domain_detected(self):
        from datasphere.agents.security_compliance import SecurityComplianceAgent
        req = make_request(business="Analyse les données hospitalières")
        out = SecurityComplianceAgent().run(req)
        assert any("HDS" in note or "HIPAA" in note or "santé" in note.lower()
                   for note in out.compliance_notes)

    def test_rbac_roles_present(self):
        from datasphere.agents.security_compliance import SecurityComplianceAgent
        req = make_request()
        out = SecurityComplianceAgent().run(req)
        assert "data_engineer" in out.rbac_config
        assert "analyst" in out.rbac_config


class TestInfrastructure:
    def test_docker_compose_generated(self):
        from datasphere.agents.infrastructure import InfrastructureAgent
        from datasphere.models.request import ArchitectureConstraints
        req = BusinessRequest(
            business_request="test",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="local-docker",
                data_warehouse="postgresql",
                orchestrator="airflow",
                ingestion="airbyte",
                transformation="dbt",
                data_lake="minio",
                bi_tool="superset",
                catalog="openmetadata",
                quality="great-expectations",
                deployment="docker-compose",
                security=["RBAC"],
                budget="low",
            )
        )
        out = InfrastructureAgent().run(req)
        assert "docker-compose.yml" in out.artifacts
        assert "services:" in out.artifacts["docker-compose.yml"]

    def test_helm_values_generated(self):
        from datasphere.agents.infrastructure import InfrastructureAgent
        req = make_request(cloud="aws")
        out = InfrastructureAgent().run(req)
        assert any("helm" in k for k in out.artifacts)

    def test_terraform_main_generated(self):
        from datasphere.agents.infrastructure import InfrastructureAgent
        req = make_request(cloud="gcp")
        req.architecture_constraints.deployment = "terraform"
        out = InfrastructureAgent().run(req)
        assert "terraform/main.tf" in out.artifacts


class TestDeployment:
    def test_github_actions_generated(self):
        from datasphere.agents.deployment import DeploymentAgent
        req = make_request()
        out = DeploymentAgent().run(req)
        assert ".github/workflows/deploy.yml" in out.artifacts
        assert "on:" in out.artifacts[".github/workflows/deploy.yml"]

    def test_pipeline_stages_present(self):
        from datasphere.agents.deployment import DeploymentAgent
        req = make_request()
        out = DeploymentAgent().run(req)
        assert len(out.pipeline_stages) >= 5
        assert any("dbt" in s.lower() for s in out.pipeline_stages)


class TestOrchestrator:
    def test_full_pipeline_aws(self, tmp_path):
        req = make_request()
        orchestrator = AgentOrchestrator()
        result = orchestrator.run(req, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None
        assert result.cloud_architect is not None
        assert result.infrastructure is not None
        assert result.cost_optimization is not None
        assert result.security_compliance is not None
        assert result.deployment is not None

    def test_full_pipeline_local_hospital(self, tmp_path):
        req = BusinessRequest(
            business_request="Analyse les données hospitalières",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="local-docker",
                data_warehouse="postgresql",
                orchestrator="dagster",
                ingestion="meltano",
                transformation="SQLMesh",
                data_lake="MinIO",
                bi_tool="metabase",
                catalog="DataHub",
                quality="Soda Core",
                deployment="Docker Compose",
                security=["JWT", "RBAC"],
                budget="low",
            )
        )
        result = AgentOrchestrator().run(req, output_dir=str(tmp_path), verbose=False)
        assert result.success or len(result.errors) == 0

    def test_artifacts_written_to_disk(self, tmp_path):
        req = make_request()
        result = AgentOrchestrator().run(req, output_dir=str(tmp_path), verbose=False)
        assert (tmp_path / "README.md").exists()
        assert len(list(tmp_path.rglob("*.md"))) >= 3

    def test_from_json_example_files(self, tmp_path):
        examples = Path("examples")
        if not examples.exists():
            pytest.skip("examples/ not found")
        for json_file in examples.glob("*.json"):
            data = json.loads(json_file.read_text())
            req = BusinessRequest(**data)
            result = AgentOrchestrator().run(req, output_dir=str(tmp_path / json_file.stem), verbose=False)
            assert result.stack_advisor is not None
