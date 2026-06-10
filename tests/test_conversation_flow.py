"""Tests du flow conversationnel en 5 étapes."""
import pytest
from datasphere.agents.proposer import generate_proposals
from datasphere.models.conversation import ArchitectureProposal
from datasphere.models.request import ArchitectureConstraints, BusinessRequest
from datasphere.agents.orchestrator import AgentOrchestrator, _step5_generate


def raw(cloud="aws", budget="medium", volume="medium", mode="batch",
        deployment="kubernetes", security=None):
    return {
        "cloud_provider":  cloud,
        "budget":          budget,
        "data_volume":     volume,
        "processing_mode": mode,
        "security":        security or ["RBAC"],
        "deployment":      deployment,
        "iac":             "helm" if deployment == "kubernetes" else "docker-compose",
        "region":          None,
        "data_warehouse":  "auto",
        "orchestrator":    "auto",
        "ingestion":       "auto",
        "transformation":  "auto",
        "data_lake":       "auto",
        "bi_tool":         "auto",
        "catalog":         "auto",
        "quality":         "auto",
    }


class TestProposer:
    def test_always_returns_2_or_3_proposals(self):
        for cloud in ("aws", "gcp", "azure", "local-docker", "kubernetes"):
            for budget in ("low", "medium", "enterprise"):
                proposals = generate_proposals(raw(cloud=cloud, budget=budget))
                assert 2 <= len(proposals) <= 3, (
                    f"Expected 2-3 proposals for {cloud}/{budget}, got {len(proposals)}"
                )

    def test_proposals_have_distinct_names(self):
        proposals = generate_proposals(raw(cloud="aws", budget="enterprise"))
        names = [p.name for p in proposals]
        assert len(names) == len(set(names)), "Proposals should have distinct names"

    def test_proposals_have_distinct_warehouses(self):
        proposals = generate_proposals(raw(cloud="aws", budget="enterprise"))
        warehouses = [p.constraints.data_warehouse for p in proposals]
        # At least 2 distinct warehouses
        assert len(set(warehouses)) >= 2

    def test_realtime_mode_includes_streaming_proposal(self):
        proposals = generate_proposals(raw(cloud="aws", mode="realtime"))
        names = [p.name.lower() for p in proposals]
        assert any("streaming" in n or "temps réel" in n or "realtime" in n for n in names)

    def test_low_budget_no_expensive_saas(self):
        proposals = generate_proposals(raw(cloud="local-docker", budget="low"))
        for p in proposals:
            assert p.constraints.data_warehouse not in ("snowflake", "databricks"), (
                f"Budget low should not propose {p.constraints.data_warehouse}"
            )

    def test_enterprise_budget_offers_best_of_breed(self):
        proposals = generate_proposals(raw(cloud="aws", budget="enterprise"))
        names = [p.name for p in proposals]
        assert any("Enterprise" in n or "Best" in n for n in names)

    def test_cost_estimates_are_non_negative(self):
        proposals = generate_proposals(raw())
        for p in proposals:
            assert p.estimated_monthly_usd >= 0

    def test_proposals_have_pros_and_cons(self):
        proposals = generate_proposals(raw())
        for p in proposals:
            assert len(p.pros) >= 2, f"Proposal '{p.name}' has too few pros"

    def test_proposals_ids_are_sequential(self):
        proposals = generate_proposals(raw())
        ids = [p.id for p in proposals]
        assert ids == list(range(1, len(proposals) + 1))

    def test_all_clouds_produce_valid_constraints(self):
        clouds = ["aws", "gcp", "azure", "local-docker", "kubernetes", "on-premise"]
        for cloud in clouds:
            proposals = generate_proposals(raw(cloud=cloud))
            for p in proposals:
                errors = p.constraints.normalize().model_dump()
                assert p.constraints.data_warehouse != "auto", (
                    f"Warehouse not resolved for cloud={cloud}"
                )


class TestStep5Generation:
    def _make_proposal(self, cloud="aws", wh="snowflake", orch="airflow",
                       ingest="airbyte", transform="dbt", budget="enterprise") -> ArchitectureProposal:
        return ArchitectureProposal(
            id=1,
            name="Test Proposal",
            tagline="Test",
            constraints=ArchitectureConstraints(
                cloud_provider=cloud,
                data_warehouse=wh,
                orchestrator=orch,
                ingestion=ingest,
                transformation=transform,
                data_lake="s3" if cloud == "aws" else "minio",
                bi_tool="superset",
                catalog="openmetadata",
                quality="great-expectations",
                deployment="kubernetes",
                iac="helm",
                security=["RBAC", "Vault"],
                budget=budget,
            ),
            pros=[],
            cons=[],
        )

    def test_step5_generates_all_artifacts(self, tmp_path):
        proposal = self._make_proposal()
        result = _step5_generate("Analyse les ventes", proposal, str(tmp_path))
        assert result.stack_advisor is not None
        assert result.infrastructure is not None
        assert result.cost_optimization is not None
        assert result.security_compliance is not None
        assert result.deployment is not None
        assert (tmp_path / "README.md").exists()

    def test_step5_local_hospital(self, tmp_path):
        proposal = self._make_proposal(
            cloud="local-docker", wh="postgresql", orch="dagster",
            ingest="meltano", transform="sqlmesh", budget="low"
        )
        proposal.constraints.deployment = "docker-compose"
        proposal.constraints.iac = "docker-compose"
        result = _step5_generate("Données hospitalières", proposal, str(tmp_path))
        assert result.success

    def test_step5_readme_contains_stack(self, tmp_path):
        proposal = self._make_proposal()
        result = _step5_generate("Test", proposal, str(tmp_path))
        readme = (tmp_path / "README.md").read_text()
        assert "snowflake" in readme.lower()
        assert "airflow" in readme.lower()


class TestOrchestratorProgrammatic:
    """Test the orchestrator in programmatic (non-interactive) mode."""

    def test_run_with_full_constraints(self, tmp_path):
        request = BusinessRequest(
            business_request="Analyse les ventes par agence",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="aws",
                data_warehouse="snowflake",
                orchestrator="airflow",
                ingestion="airbyte",
                transformation="dbt Core",
                data_lake="S3",
                bi_tool="superset",
                catalog="openmetadata",
                quality="great-expectations",
                deployment="kubernetes",
                iac="terraform",
                security=["RBAC", "Vault", "RLS"],
                budget="enterprise",
            )
        )
        result = AgentOrchestrator().run(request, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None
        assert result.cost_optimization.total_monthly_usd > 0

    def test_run_with_auto_constraints_picks_first_proposal(self, tmp_path):
        request = BusinessRequest(
            business_request="Analyse des données",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="gcp",
                data_warehouse="auto",
                orchestrator="auto",
                ingestion="auto",
                transformation="auto",
                data_lake="auto",
                bi_tool="auto",
                catalog="auto",
                quality="auto",
                deployment="kubernetes",
                iac="helm",
                security=["RBAC"],
                budget="medium",
            )
        )
        result = AgentOrchestrator().run(request, output_dir=str(tmp_path), verbose=False)
        assert result.success

    def test_healthcare_domain_triggers_compliance(self, tmp_path):
        request = BusinessRequest(
            business_request="Analyse des données hospitalières et patients",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="local-docker",
                data_warehouse="postgresql",
                orchestrator="dagster",
                ingestion="meltano",
                transformation="sqlmesh",
                data_lake="minio",
                bi_tool="metabase",
                catalog="datahub",
                quality="soda-core",
                deployment="docker-compose",
                iac="docker-compose",
                security=["JWT", "RBAC"],
                budget="low",
            )
        )
        result = AgentOrchestrator().run(request, output_dir=str(tmp_path), verbose=False)
        assert result.security_compliance is not None
        notes = result.security_compliance.compliance_notes
        assert any("HDS" in n or "santé" in n.lower() or "HIPAA" in n for n in notes)

    def test_json_examples_work_end_to_end(self, tmp_path):
        from pathlib import Path
        import json
        examples = Path("examples")
        if not examples.exists():
            pytest.skip("examples/ not found")
        for json_file in examples.glob("*.json"):
            data = json.loads(json_file.read_text())
            request = BusinessRequest(**data)
            result = AgentOrchestrator().run(
                request, output_dir=str(tmp_path / json_file.stem), verbose=False
            )
            assert result.stack_advisor is not None, f"Failed for {json_file.name}"
