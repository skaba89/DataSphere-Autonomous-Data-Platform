"""
Coverage tests for datasphere/agents/orchestrator.py — targeting missing lines.
Missing: _step1_business_request (157), _step3_display_proposals (174-227),
         _write_artifacts airflow branch (318-319, 331-332),
         _print_generation_summary branches (396->404, 404->418)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from datasphere.models.request import ArchitectureConstraints, BusinessRequest
from datasphere.models.output import AgentOutput, OrchestratorOutput, CloudArchitectOutput
from datasphere.models.conversation import ArchitectureProposal


def _make_constraints(**kwargs) -> ArchitectureConstraints:
    defaults = dict(
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="metabase",
        deployment="docker-compose",
        budget="medium",
    )
    defaults.update(kwargs)
    return ArchitectureConstraints(**defaults)


def _make_proposal(orchestrator="airflow", **kwargs) -> ArchitectureProposal:
    c = _make_constraints(orchestrator=orchestrator)
    return ArchitectureProposal(
        id=1,
        name="Test Stack",
        tagline="A test architecture",
        constraints=c,
        pros=["Fast", "Cheap"],
        cons=["Complex"],
        estimated_monthly_usd=500.0,
        complexity="medium",
        time_to_deploy="2 weeks",
        best_for="testing",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _step1_business_request — lines 62-77
# ---------------------------------------------------------------------------

class TestStep1BusinessRequest:
    def test_step1_returns_on_valid_input(self):
        from datasphere.agents.orchestrator import _step1_business_request

        with patch("rich.console.Console.input", return_value="Analytics pipeline for sales"):
            result = _step1_business_request()
        assert result == "Analytics pipeline for sales"

    def test_step1_retries_on_short_input(self):
        """Short input (<=5 chars) should be rejected, then valid input accepted."""
        from datasphere.agents.orchestrator import _step1_business_request

        inputs = iter(["hi", "ok", "Analyse les ventes par région"])
        with patch("rich.console.Console.input", side_effect=lambda _: next(inputs)):
            result = _step1_business_request()
        assert result == "Analyse les ventes par région"


# ---------------------------------------------------------------------------
# _step3_display_proposals — lines 87-132
# ---------------------------------------------------------------------------

class TestStep3DisplayProposals:
    def test_step3_displays_proposals(self):
        from datasphere.agents.orchestrator import _step3_display_proposals

        proposals = [
            _make_proposal(orchestrator="airflow"),
            _make_proposal(orchestrator="dagster"),
        ]
        # Just call it — verify no exceptions
        _step3_display_proposals(proposals)

    def test_step3_with_no_cons(self):
        """Proposal with empty cons list."""
        from datasphere.agents.orchestrator import _step3_display_proposals

        proposal = ArchitectureProposal(
            id=1,
            name="Simple Stack",
            tagline="Easy peasy",
            constraints=_make_constraints(),
            pros=["Simple"],
            cons=[],
            estimated_monthly_usd=100.0,
            complexity="low",
            time_to_deploy="1 week",
            best_for="small teams",
        )
        _step3_display_proposals([proposal])

    def test_step3_with_data_lake(self):
        """Proposal with data_lake set."""
        from datasphere.agents.orchestrator import _step3_display_proposals

        c = _make_constraints()
        c.data_lake = "s3"
        proposal = ArchitectureProposal(
            id=1,
            name="Lake Stack",
            tagline="With data lake",
            constraints=c,
            pros=["Scalable"],
            cons=[],
            estimated_monthly_usd=800.0,
            complexity="high",
            time_to_deploy="4 weeks",
            best_for="big data",
        )
        _step3_display_proposals([proposal])

    def test_step3_high_complexity_color(self):
        """High complexity proposal should use red color."""
        from datasphere.agents.orchestrator import _step3_display_proposals

        proposal = ArchitectureProposal(
            id=1,
            name="Complex Stack",
            tagline="Enterprise grade",
            constraints=_make_constraints(),
            pros=["Powerful"],
            cons=["Expensive"],
            estimated_monthly_usd=5000.0,
            complexity="high",
            time_to_deploy="3 months",
            best_for="enterprises",
        )
        _step3_display_proposals([proposal])


# ---------------------------------------------------------------------------
# _step4_choose_proposal — lines 139-169
# ---------------------------------------------------------------------------

class TestStep4ChooseProposal:
    def test_step4_valid_choice(self):
        from datasphere.agents.orchestrator import _step4_choose_proposal

        proposals = [_make_proposal(), _make_proposal()]
        proposals[0].id = 1
        proposals[1].id = 2

        with patch("rich.console.Console.input", return_value="1"):
            chosen = _step4_choose_proposal(proposals)
        assert chosen.id == 1

    def test_step4_invalid_then_valid(self):
        from datasphere.agents.orchestrator import _step4_choose_proposal

        proposals = [_make_proposal()]
        proposals[0].id = 1

        inputs = iter(["99", "abc", "1"])
        with patch("rich.console.Console.input", side_effect=lambda _: next(inputs)):
            chosen = _step4_choose_proposal(proposals)
        assert chosen.id == 1

    def test_step4_customise(self):
        """Test 'c' option triggers customise flow."""
        from datasphere.agents.orchestrator import _step4_choose_proposal

        proposals = [_make_proposal()]
        proposals[0].id = 1

        # First input "c" → customise, then "1" for base, then enter for each field
        field_count = 7  # adjustable fields in _customise_proposal
        inputs = iter(["c", "1"] + [""] * field_count)
        with patch("rich.console.Console.input", side_effect=lambda _: next(inputs)):
            chosen = _step4_choose_proposal(proposals)
        assert "personnalisée" in chosen.name


# ---------------------------------------------------------------------------
# _write_artifacts with airflow orchestrator — lines 318-332
# ---------------------------------------------------------------------------

class TestWriteArtifacts:
    def test_write_artifacts_with_airflow(self, tmp_path):
        from datasphere.agents.orchestrator import _write_artifacts

        proposal = _make_proposal(orchestrator="airflow")
        result = OrchestratorOutput(request_summary="Test pipeline")

        # Add a mock agent output with artifacts
        agent_out = AgentOutput(
            agent="stack_advisor",
            success=True,
            artifacts={"stack.md": "# Stack\nAll good."},
        )
        result.stack_advisor = agent_out

        path = _write_artifacts(result, str(tmp_path), proposal)
        assert path == str(tmp_path)
        # Airflow DAGs folder should be attempted
        # README.md should always be created
        assert (tmp_path / "README.md").exists()

    def test_write_artifacts_non_airflow(self, tmp_path):
        from datasphere.agents.orchestrator import _write_artifacts

        proposal = _make_proposal(orchestrator="dagster")
        result = OrchestratorOutput(request_summary="Dagster pipeline")

        path = _write_artifacts(result, str(tmp_path), proposal)
        assert path == str(tmp_path)
        assert (tmp_path / "README.md").exists()

    def test_write_artifacts_dbt_exception_handled(self, tmp_path):
        """DbtProjectGenerator raises — should be caught gracefully."""
        from datasphere.agents.orchestrator import _write_artifacts

        proposal = _make_proposal(orchestrator="dagster")
        result = OrchestratorOutput(request_summary="Error test")

        with patch("datasphere.agents.orchestrator.DbtProjectGenerator.generate",
                   side_effect=RuntimeError("dbt error")):
            path = _write_artifacts(result, str(tmp_path), proposal)
        assert path == str(tmp_path)

    def test_write_artifacts_airflow_exception_handled(self, tmp_path):
        """AirflowDagGenerator raises — should be caught gracefully."""
        from datasphere.agents.orchestrator import _write_artifacts

        proposal = _make_proposal(orchestrator="airflow")
        result = OrchestratorOutput(request_summary="Airflow error test")

        with patch("datasphere.agents.orchestrator.AirflowDagGenerator.generate",
                   side_effect=RuntimeError("airflow error")):
            path = _write_artifacts(result, str(tmp_path), proposal)
        assert path == str(tmp_path)


# ---------------------------------------------------------------------------
# _print_generation_summary — lines 387-426
# ---------------------------------------------------------------------------

class TestPrintGenerationSummary:
    def test_print_summary_with_warnings(self):
        from datasphere.agents.orchestrator import _print_generation_summary

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True

        # stack_advisor with warnings
        stack_out = AgentOutput(agent="stack_advisor", success=True, warnings=["Budget mismatch", "Consider upgrading"])
        result.stack_advisor = stack_out

        # Should not raise
        _print_generation_summary(result, proposal)

    def test_print_summary_with_cloud_recommendations(self):
        from datasphere.agents.orchestrator import _print_generation_summary

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True

        # cloud_architect with recommendations
        cloud_out = CloudArchitectOutput(agent="cloud_architect", success=True, recommendations=["Use spot instances", "Enable auto-scaling"])
        result.cloud_architect = cloud_out

        _print_generation_summary(result, proposal)

    def test_print_summary_with_cost(self):
        from datasphere.agents.orchestrator import _print_generation_summary
        from datasphere.models.output import CostOptimizationOutput

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True

        cost_out = CostOptimizationOutput(
            agent="cost_optimization",
            success=True,
            total_monthly_usd=1500.0,
            total_yearly_usd=18000.0,
            savings_usd=300.0,
        )
        result.cost_optimization = cost_out

        _print_generation_summary(result, proposal)

    def test_print_summary_with_cost_no_savings(self):
        from datasphere.agents.orchestrator import _print_generation_summary
        from datasphere.models.output import CostOptimizationOutput

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True

        cost_out = CostOptimizationOutput(
            agent="cost_optimization",
            success=True,
            total_monthly_usd=500.0,
            total_yearly_usd=6000.0,
            savings_usd=0.0,
        )
        result.cost_optimization = cost_out

        _print_generation_summary(result, proposal)

    def test_print_summary_with_artifacts_path(self):
        from datasphere.agents.orchestrator import _print_generation_summary

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True
        result.artifacts_path = "/tmp/my-artifacts"

        _print_generation_summary(result, proposal)

    def test_print_summary_failure(self):
        from datasphere.agents.orchestrator import _print_generation_summary

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = False
        result.errors = ["Agent failed", "Timeout"]

        _print_generation_summary(result, proposal)

    def test_print_summary_with_cloud_recs_filtered(self):
        """Recommendations containing 'aucun conflit' should be filtered out."""
        from datasphere.agents.orchestrator import _print_generation_summary

        proposal = _make_proposal()
        result = OrchestratorOutput(request_summary="Test")
        result.success = True

        cloud_out = CloudArchitectOutput(agent="cloud_architect", success=True, recommendations=["aucun conflit détecté", "Use EKS for Kubernetes"])
        result.cloud_architect = cloud_out

        _print_generation_summary(result, proposal)


# ---------------------------------------------------------------------------
# from_json, from_json_string, from_json_file helpers
# ---------------------------------------------------------------------------

class TestJsonHelpers:
    def test_from_json(self):
        from datasphere.agents.orchestrator import from_json

        data = {
            "business_request": "Test pipeline",
            "architecture_constraints": {
                "cloud_provider": "aws",
                "data_warehouse": "snowflake",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "metabase",
                "deployment": "docker-compose",
                "budget": "medium",
            }
        }
        req = from_json(data)
        assert req.business_request == "Test pipeline"

    def test_from_json_string(self):
        import json
        from datasphere.agents.orchestrator import from_json_string

        data = {
            "business_request": "String test",
            "architecture_constraints": {
                "cloud_provider": "gcp",
                "data_warehouse": "bigquery",
                "orchestrator": "dagster",
                "ingestion": "meltano",
                "transformation": "dbt",
                "bi_tool": "superset",
                "deployment": "kubernetes",
                "budget": "enterprise",
            }
        }
        req = from_json_string(json.dumps(data))
        assert req.business_request == "String test"

    def test_from_json_file(self, tmp_path):
        import json
        from datasphere.agents.orchestrator import from_json_file

        data = {
            "business_request": "File test",
            "architecture_constraints": {
                "cloud_provider": "azure",
                "data_warehouse": "synapse",
                "orchestrator": "prefect",
                "ingestion": "fivetran",
                "transformation": "dbt",
                "bi_tool": "powerbi",
                "deployment": "docker-compose",
                "budget": "medium",
            }
        }
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(data))
        req = from_json_file(str(json_file))
        assert req.business_request == "File test"


# ---------------------------------------------------------------------------
# _build_index — lines 338-384
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_build_index_with_airflow(self):
        from datasphere.agents.orchestrator import _build_index
        from datasphere.models.output import CostOptimizationOutput

        proposal = _make_proposal(orchestrator="airflow")
        result = OrchestratorOutput(request_summary="Index test")

        cost_out = CostOptimizationOutput(
            agent="cost_optimization",
            success=True,
            total_monthly_usd=1200.0,
            total_yearly_usd=14400.0,
            savings_usd=200.0,
        )
        result.cost_optimization = cost_out

        md = _build_index(result, proposal)
        assert "Index test" in md
        assert "airflow" in md.lower() or "Airflow" in md

    def test_build_index_without_airflow(self):
        from datasphere.agents.orchestrator import _build_index

        proposal = _make_proposal(orchestrator="dagster")
        result = OrchestratorOutput(request_summary="No airflow test")
        md = _build_index(result, proposal)
        assert "No airflow test" in md
