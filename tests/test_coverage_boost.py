"""
Targeted tests to boost coverage on:
  - datasphere/agents/dialogue.py        (target: 75%+)
  - datasphere/agents/mode_router.py     (target: 75%+)
  - datasphere/agents/orchestrator.py    (target: 75%+)
"""
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from datasphere.models.request import BusinessRequest, ArchitectureConstraints
from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.models.conversation import ArchitectureProposal
from datasphere.models.output import OrchestratorOutput, AgentOutput


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_explicit_stack(**overrides) -> ExplicitStack:
    defaults = dict(
        business_request="Analyse les ventes par agence",
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="superset",
        deployment="kubernetes",
        security=["RBAC", "jwt"],
        budget="medium",
        data_volume="medium",
        data_lake="s3",
    )
    defaults.update(overrides)
    return ExplicitStack(**defaults)


def make_recommendation_context(**overrides) -> RecommendationContext:
    defaults = dict(
        business_request="Analyse les données hospitalières",
        budget="medium",
        data_volume="medium",
        security_level="rbac",
        team_size="small",
        processing_mode="batch",
        cloud_preference="aws",
    )
    defaults.update(overrides)
    return RecommendationContext(**defaults)


def make_proposal(cloud="aws", warehouse="snowflake", orchestrator="airflow") -> ArchitectureProposal:
    return ArchitectureProposal(
        id=1,
        name="Stack Test",
        tagline="For testing",
        constraints=ArchitectureConstraints(
            cloud_provider=cloud,
            data_warehouse=warehouse,
            orchestrator=orchestrator,
            ingestion="airbyte",
            transformation="dbt",
            data_lake="s3",
            bi_tool="superset",
            catalog="openmetadata",
            quality="great-expectations",
            deployment="kubernetes",
            iac="helm",
            security=["RBAC"],
            budget="medium",
        ),
        pros=["Fast", "Reliable"],
        cons=["Cost"],
        estimated_monthly_usd=500.0,
        complexity="medium",
        time_to_deploy="2 weeks",
        best_for="Analytics teams",
    )


def make_business_request(**overrides) -> BusinessRequest:
    defaults = dict(
        business_request="Analyse les ventes",
        architecture_constraints=ArchitectureConstraints(
            cloud_provider="aws",
            data_warehouse="snowflake",
            orchestrator="airflow",
            ingestion="airbyte",
            transformation="dbt",
            data_lake="s3",
            bi_tool="superset",
            catalog="openmetadata",
            quality="great-expectations",
            deployment="kubernetes",
            iac="helm",
            security=["RBAC", "Vault"],
            budget="enterprise",
        ),
    )
    defaults.update(overrides)
    return BusinessRequest(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue tests (dialogue.py lines 57–141)
# ─────────────────────────────────────────────────────────────────────────────

class TestDialogueAsk:
    """Unit tests for the _ask helper in dialogue.py."""

    def test_ask_valid_choice(self):
        """_ask returns the key for a valid numeric choice."""
        from datasphere.agents.dialogue import _ask, CLOUD_OPTIONS
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.return_value = "1"
            result = _ask("Choose cloud", CLOUD_OPTIONS)
        assert result == CLOUD_OPTIONS[0][0]

    def test_ask_allow_skip_zero(self):
        """_ask returns 'auto' when allow_skip=True and user enters 0."""
        from datasphere.agents.dialogue import _ask, CLOUD_OPTIONS
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.return_value = "0"
            result = _ask("Choose", CLOUD_OPTIONS, allow_skip=True)
        assert result == "auto"

    def test_ask_invalid_then_valid(self):
        """_ask loops on invalid input then succeeds."""
        from datasphere.agents.dialogue import _ask, BUDGET_OPTIONS
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = ["abc", "999", "2"]
            result = _ask("Choose budget", BUDGET_OPTIONS)
        assert result == BUDGET_OPTIONS[1][0]

    def test_ask_text_returns_input(self):
        """_ask_text returns the typed value."""
        from datasphere.agents.dialogue import _ask_text
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.return_value = "eu-west-1"
            result = _ask_text("Région AWS", default="eu-west-1")
        assert result == "eu-west-1"

    def test_ask_text_uses_default_on_empty(self):
        """_ask_text falls back to default when user presses Enter."""
        from datasphere.agents.dialogue import _ask_text
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.return_value = ""
            result = _ask_text("Région", default="eu-west-3")
        assert result == "eu-west-3"

    def test_ask_text_no_default(self):
        """_ask_text with no default returns empty string when Enter pressed."""
        from datasphere.agents.dialogue import _ask_text
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.return_value = ""
            result = _ask_text("Input something")
        assert result == ""


class TestDialogueCollectConstraints:
    """Tests for collect_constraints — the main dialogue function."""

    def _mock_inputs_for_cloud(self, cloud_choice_num: int, region: str = "eu-west-1"):
        """Returns a list of mock input values for all prompts (6 choices + optional region)."""
        return [
            str(cloud_choice_num),  # cloud
            "1",                    # budget (low)
            "1",                    # volume (small)
            "1",                    # mode (batch)
            "1",                    # security (simple)
            "1",                    # deployment (docker-compose)
            region,                 # region (only for aws/azure/gcp)
        ]

    def test_collect_constraints_local_docker(self):
        """collect_constraints works end-to-end with local-docker (no region asked)."""
        from datasphere.agents.dialogue import collect_constraints
        # local-docker is option 1
        inputs = ["1", "1", "1", "1", "1", "1"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("Analyse les ventes")
        assert result["cloud_provider"] == "local-docker"
        assert result["budget"] == "low"
        assert result["data_volume"] == "small"
        assert result["processing_mode"] == "batch"
        assert result["security"] == ["jwt"]
        assert result["deployment"] == "docker-compose"
        assert result["iac"] == "docker-compose"
        assert result["region"] is None
        # auto fields
        assert result["data_warehouse"] == "auto"
        assert result["orchestrator"] == "auto"

    def test_collect_constraints_aws_with_region(self):
        """collect_constraints asks for region when cloud is AWS (option 2)."""
        from datasphere.agents.dialogue import collect_constraints
        # aws is option 2, budget medium (2), volume medium (2), realtime (2),
        # rbac (2), kubernetes (2), region typed
        inputs = ["2", "2", "2", "2", "2", "2", "us-east-1"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("Process orders")
        assert result["cloud_provider"] == "aws"
        assert result["region"] == "us-east-1"
        assert result["security"] == ["RBAC", "jwt"]
        assert result["iac"] == "helm"

    def test_collect_constraints_azure_with_region(self):
        """collect_constraints asks for region when cloud is Azure (option 3)."""
        from datasphere.agents.dialogue import collect_constraints
        # azure is option 3
        inputs = ["3", "2", "2", "2", "2", "2", "westeurope"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("Azure pipeline")
        assert result["cloud_provider"] == "azure"
        assert result["region"] == "westeurope"

    def test_collect_constraints_gcp_with_region(self):
        """collect_constraints asks for region when cloud is GCP (option 4)."""
        from datasphere.agents.dialogue import collect_constraints
        # gcp is option 4
        inputs = ["4", "1", "1", "1", "1", "1", "europe-west1"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("GCP analytics")
        assert result["cloud_provider"] == "gcp"
        assert result["region"] == "europe-west1"

    def test_collect_constraints_enterprise_security(self):
        """enterprise security level maps to RBAC+RLS+Vault."""
        from datasphere.agents.dialogue import collect_constraints
        # local-docker, enterprise budget (3), large volume (3), batch (1),
        # enterprise security (3), managed deployment (3)
        inputs = ["1", "3", "3", "1", "3", "3"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("Enterprise analytics")
        assert result["security"] == ["RBAC", "RLS", "Vault"]
        assert result["deployment"] == "managed"
        assert result["iac"] == "terraform"

    def test_collect_constraints_kubernetes_deployment(self):
        """kubernetes deployment maps to helm iac."""
        from datasphere.agents.dialogue import collect_constraints
        # local-docker, low, small, batch, simple, kubernetes (2)
        inputs = ["1", "1", "1", "1", "1", "2"]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("K8s pipeline")
        assert result["deployment"] == "kubernetes"
        assert result["iac"] == "helm"

    def test_collect_constraints_aws_default_region(self):
        """When user presses Enter on region, default is used."""
        from datasphere.agents.dialogue import collect_constraints
        # aws (2), low, small, batch, simple, docker-compose, empty region
        inputs = ["2", "1", "1", "1", "1", "1", ""]
        with patch("datasphere.agents.dialogue.console") as mock_console:
            mock_console.input.side_effect = inputs
            result = collect_constraints("Default region")
        assert result["cloud_provider"] == "aws"
        assert result["region"] == "eu-west-1"  # default


# ─────────────────────────────────────────────────────────────────────────────
# Mode Router tests (mode_router.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunExplicit:
    """Tests for run_explicit() in mode_router.py."""

    def test_run_explicit_returns_orchestrator_output(self, tmp_path):
        """run_explicit produces an OrchestratorOutput with all agents filled."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack()
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert isinstance(result, OrchestratorOutput)
        assert result.stack_advisor is not None
        assert result.cloud_architect is not None

    def test_run_explicit_verbose_prints_summary(self, tmp_path):
        """run_explicit with verbose=True calls _print_mode1_summary."""
        from datasphere.agents.mode_router import run_explicit, _print_mode1_summary
        stack = make_explicit_stack()
        with patch("datasphere.agents.mode_router._print_mode1_summary") as mock_print:
            run_explicit(stack, output_dir=str(tmp_path), verbose=True)
        mock_print.assert_called_once_with(stack)

    def test_run_explicit_no_output_dir(self):
        """run_explicit with output_dir=None skips artifact writing (artifacts_path stays empty)."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack()
        result = run_explicit(stack, output_dir=None, verbose=False)
        assert not result.artifacts_path  # empty string = no artifacts written

    def test_run_explicit_low_budget(self, tmp_path):
        """run_explicit with low budget stack completes."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack(
            cloud_provider="local-docker",
            data_warehouse="postgresql",
            orchestrator="dagster",
            ingestion="meltano",
            transformation="dbt",
            bi_tool="metabase",
            deployment="docker-compose",
            budget="low",
            data_lake=None,
        )
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_explicit_enterprise_budget(self, tmp_path):
        """run_explicit with enterprise budget stack completes."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack(budget="enterprise", data_volume="xlarge")
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_explicit_gcp_stack(self, tmp_path):
        """run_explicit with GCP cloud provider completes."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack(
            cloud_provider="gcp",
            data_warehouse="bigquery",
        )
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.cloud_architect is not None

    def test_run_explicit_azure_stack(self, tmp_path):
        """run_explicit with Azure cloud provider completes."""
        from datasphere.agents.mode_router import run_explicit
        stack = make_explicit_stack(
            cloud_provider="azure",
            data_warehouse="azure-synapse",
        )
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.cloud_architect is not None

    def test_print_mode1_summary_no_datalake(self):
        """_print_mode1_summary handles None data_lake without error."""
        from datasphere.agents.mode_router import _print_mode1_summary
        stack = make_explicit_stack(data_lake=None)
        with patch("datasphere.agents.mode_router.console"):
            _print_mode1_summary(stack)  # must not raise


class TestRunRecommended:
    """Tests for run_recommended() in mode_router.py."""

    def test_run_recommended_returns_output(self, tmp_path):
        """run_recommended produces an OrchestratorOutput."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context()
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert isinstance(result, OrchestratorOutput)
        assert result.stack_advisor is not None

    def test_run_recommended_verbose_false_picks_first_proposal(self, tmp_path):
        """run_recommended with verbose=False picks proposals[0] without human input."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context()
        # verbose=False → no console interaction, should complete cleanly
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result is not None

    def test_run_recommended_low_budget(self, tmp_path):
        """run_recommended with low budget generates open-source stack."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(budget="low", must_be_open_source=True)
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_recommended_enterprise_budget(self, tmp_path):
        """run_recommended with enterprise budget completes."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(budget="enterprise", team_size="large")
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_recommended_cloud_aws(self, tmp_path):
        """run_recommended with AWS cloud preference completes."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(cloud_preference="aws")
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_recommended_cloud_gcp(self, tmp_path):
        """run_recommended with GCP cloud preference completes."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(cloud_preference="gcp")
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_recommended_cloud_azure(self, tmp_path):
        """run_recommended with Azure cloud preference completes."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(cloud_preference="azure")
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_recommended_realtime_mode(self, tmp_path):
        """run_recommended with realtime processing mode completes."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context(processing_mode="realtime")
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result is not None

    def test_run_recommended_no_output_dir(self):
        """run_recommended with output_dir=None skips artifact writing."""
        from datasphere.agents.mode_router import run_recommended
        ctx = make_recommendation_context()
        result = run_recommended(ctx, output_dir=None, verbose=False)
        assert not result.artifacts_path  # empty string = no artifacts written

    def test_print_mode2_context(self):
        """_print_mode2_context renders without error."""
        from datasphere.agents.mode_router import _print_mode2_context
        ctx = make_recommendation_context(
            must_be_open_source=True,
            existing_tools=["spark"],
            compliance_requirements=["RGPD"],
        )
        with patch("datasphere.agents.mode_router.console"):
            _print_mode2_context(ctx)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator tests (orchestrator.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestStep5Generate:
    """Tests for _step5_generate — the core generation pipeline."""

    def test_step5_generates_all_agents(self, tmp_path):
        """_step5_generate runs all 6 agents and returns complete output."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal()
        result = _step5_generate("Analyse les ventes", proposal, str(tmp_path))
        assert result.stack_advisor is not None
        assert result.cloud_architect is not None
        assert result.infrastructure is not None
        assert result.cost_optimization is not None
        assert result.security_compliance is not None
        assert result.deployment is not None

    def test_step5_success_true_on_complete(self, tmp_path):
        """_step5_generate sets success=True when no errors occur."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal()
        result = _step5_generate("Test business request", proposal, str(tmp_path))
        assert result.success is True
        assert result.errors == []

    def test_step5_request_summary_set(self, tmp_path):
        """_step5_generate stores the business request in request_summary."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal()
        result = _step5_generate("My unique request", proposal, str(tmp_path))
        assert result.request_summary == "My unique request"

    def test_step5_artifacts_path_set(self, tmp_path):
        """_step5_generate sets artifacts_path when output_dir provided."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal()
        result = _step5_generate("Test", proposal, str(tmp_path))
        assert result.artifacts_path is not None
        assert str(tmp_path) in result.artifacts_path

    def test_step5_no_output_dir(self):
        """_step5_generate skips artifact writing when output_dir=None."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal()
        result = _step5_generate("Test", proposal, None)
        assert not result.artifacts_path  # empty string = no artifacts written

    def test_step5_airflow_generates_dags(self, tmp_path):
        """_step5_generate with airflow orchestrator produces dag files."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal(orchestrator="airflow")
        result = _step5_generate("Airflow pipeline", proposal, str(tmp_path))
        assert result.artifacts_path is not None

    def test_step5_non_airflow_orchestrator(self, tmp_path):
        """_step5_generate with dagster orchestrator completes without dag error."""
        from datasphere.agents.orchestrator import _step5_generate
        proposal = make_proposal(orchestrator="dagster")
        result = _step5_generate("Dagster pipeline", proposal, str(tmp_path))
        assert result.stack_advisor is not None

    def test_step5_handles_agent_failure(self, tmp_path):
        """_step5_generate accumulates errors when an agent fails."""
        from datasphere.agents.orchestrator import _step5_generate
        from datasphere.agents.stack_advisor import StackAdvisorAgent

        failing_output = AgentOutput(agent="stack-advisor", success=False, errors=["Stack validation failed"])

        with patch.object(StackAdvisorAgent, "run", return_value=failing_output):
            proposal = make_proposal()
            result = _step5_generate("Test failure", proposal, str(tmp_path))

        assert result.success is False
        assert "Stack validation failed" in result.errors


class TestAgentOrchestratorRun:
    """Tests for AgentOrchestrator.run() — programmatic mode."""

    def test_run_explicit_mode_explicit_stack(self, tmp_path):
        """AgentOrchestrator.run() with explicit warehouse skips proposal."""
        from datasphere.agents.orchestrator import AgentOrchestrator
        req = make_business_request()
        orch = AgentOrchestrator()
        result = orch.run(req, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None
        assert result.success is True

    def test_run_recommended_mode_auto_warehouse(self, tmp_path):
        """AgentOrchestrator.run() with auto warehouse generates proposals."""
        from datasphere.agents.orchestrator import AgentOrchestrator
        from datasphere.models.request import ArchitectureConstraints
        req = BusinessRequest(
            business_request="Auto-recommend me a stack",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="local-docker",
                data_warehouse="auto",
                orchestrator="auto",
                ingestion="auto",
                transformation="auto",
                data_lake="auto",
                bi_tool="auto",
                catalog="auto",
                quality="auto",
                deployment="docker-compose",
                iac="docker-compose",
                security=["RBAC"],
                budget="low",
            )
        )
        orch = AgentOrchestrator()
        result = orch.run(req, output_dir=str(tmp_path), verbose=False)
        assert result.stack_advisor is not None

    def test_run_output_has_all_agents(self, tmp_path):
        """AgentOrchestrator.run() result has all 6 agent outputs populated."""
        from datasphere.agents.orchestrator import AgentOrchestrator
        req = make_business_request()
        result = AgentOrchestrator().run(req, output_dir=str(tmp_path), verbose=False)
        for attr in ("stack_advisor", "cloud_architect", "infrastructure",
                     "cost_optimization", "security_compliance", "deployment"):
            assert getattr(result, attr) is not None, f"{attr} should not be None"

    def test_run_artifacts_written(self, tmp_path):
        """AgentOrchestrator.run() writes README.md and other artifacts."""
        from datasphere.agents.orchestrator import AgentOrchestrator
        req = make_business_request()
        result = AgentOrchestrator().run(req, output_dir=str(tmp_path), verbose=False)
        assert (tmp_path / "README.md").exists()

    def test_run_verbose_true_displays_proposals(self, tmp_path):
        """AgentOrchestrator.run() with verbose=True on auto-mode calls display."""
        from datasphere.agents.orchestrator import AgentOrchestrator
        from datasphere.models.request import ArchitectureConstraints
        req = BusinessRequest(
            business_request="Verbose test",
            architecture_constraints=ArchitectureConstraints(
                cloud_provider="local-docker",
                data_warehouse="auto",
                orchestrator="auto",
                ingestion="auto",
                transformation="auto",
                data_lake="auto",
                bi_tool="auto",
                catalog="auto",
                quality="auto",
                deployment="docker-compose",
                iac="docker-compose",
                security=["RBAC"],
                budget="low",
            )
        )
        with patch("datasphere.agents.orchestrator._step3_display_proposals") as mock_display:
            AgentOrchestrator().run(req, output_dir=str(tmp_path), verbose=True)
        mock_display.assert_called_once()


class TestOrchestratorHelpers:
    """Tests for module-level helper functions in orchestrator.py."""

    def test_from_json_round_trip(self):
        """from_json parses a dict into a BusinessRequest."""
        from datasphere.agents.orchestrator import from_json
        data = {
            "business_request": "Test",
            "architecture_constraints": {
                "cloud_provider": "aws",
                "data_warehouse": "snowflake",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "superset",
                "deployment": "kubernetes",
                "security": ["RBAC"],
                "budget": "medium",
            }
        }
        req = from_json(data)
        assert req.business_request == "Test"
        assert req.architecture_constraints.cloud_provider == "aws"

    def test_from_json_string(self):
        """from_json_string parses a JSON string."""
        import json
        from datasphere.agents.orchestrator import from_json_string
        data = {
            "business_request": "JSON string test",
            "architecture_constraints": {
                "cloud_provider": "gcp",
                "data_warehouse": "bigquery",
                "orchestrator": "dagster",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "metabase",
                "deployment": "kubernetes",
                "security": ["RBAC"],
                "budget": "medium",
            }
        }
        req = from_json_string(json.dumps(data))
        assert req.business_request == "JSON string test"

    def test_from_json_file(self, tmp_path):
        """from_json_file reads a JSON file and returns a BusinessRequest."""
        import json
        from datasphere.agents.orchestrator import from_json_file
        data = {
            "business_request": "File test",
            "architecture_constraints": {
                "cloud_provider": "azure",
                "data_warehouse": "azure-synapse",
                "orchestrator": "prefect",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "powerbi",
                "deployment": "managed",
                "security": ["RBAC"],
                "budget": "enterprise",
            }
        }
        f = tmp_path / "request.json"
        f.write_text(json.dumps(data))
        req = from_json_file(str(f))
        assert req.business_request == "File test"

    def test_step3_display_proposals(self):
        """_step3_display_proposals renders without error for multiple proposals."""
        from datasphere.agents.orchestrator import _step3_display_proposals
        proposals = [make_proposal(), make_proposal(cloud="gcp", warehouse="bigquery")]
        proposals[1] = ArchitectureProposal(
            id=2,
            name="GCP Stack",
            tagline="GCP optimised",
            constraints=proposals[1].constraints,
            pros=["Managed", "Scalable"],
            cons=[],
            estimated_monthly_usd=1200.0,
            complexity="high",
            time_to_deploy="3 weeks",
            best_for="Large teams",
        )
        with patch("datasphere.agents.orchestrator.console"):
            _step3_display_proposals(proposals)  # must not raise

    def test_build_index_includes_cost(self):
        """_build_index includes cost section when cost_optimization is set."""
        from datasphere.agents.orchestrator import _build_index
        from datasphere.models.output import CostOptimizationOutput
        result = OrchestratorOutput(request_summary="Test")
        result.cost_optimization = CostOptimizationOutput(
            total_monthly_usd=500.0,
            total_yearly_usd=6000.0,
            savings_usd=200.0,
            optimizations=[],
        )
        proposal = make_proposal()
        index = _build_index(result, proposal)
        assert "500" in index
        assert "Résumé des coûts" in index

    def test_build_index_airflow_section(self):
        """_build_index includes Airflow DAG section when orchestrator is airflow."""
        from datasphere.agents.orchestrator import _build_index
        result = OrchestratorOutput(request_summary="Airflow test")
        proposal = make_proposal(orchestrator="airflow")
        index = _build_index(result, proposal)
        assert "Airflow DAGs" in index

    def test_build_index_no_airflow_section(self):
        """_build_index omits Airflow section for non-airflow orchestrators."""
        from datasphere.agents.orchestrator import _build_index
        result = OrchestratorOutput(request_summary="Dagster test")
        proposal = make_proposal(orchestrator="dagster")
        index = _build_index(result, proposal)
        assert "Airflow DAGs" not in index


class TestModeRouterExplicitConstraints:
    """Tests specifically for _interactive_mode1/2 constraint mapping logic."""

    def test_explicit_stack_to_constraints_no_datalake(self):
        """ExplicitStack.to_architecture_constraints handles None data_lake."""
        stack = make_explicit_stack(data_lake=None)
        constraints = stack.to_architecture_constraints()
        assert constraints.data_lake is None

    def test_explicit_stack_security_rbac(self):
        """ExplicitStack with RBAC security maps correctly."""
        stack = make_explicit_stack(security=["RBAC", "jwt"])
        constraints = stack.to_architecture_constraints()
        assert "RBAC" in constraints.security

    def test_recommendation_context_to_raw_open_source_overrides_budget(self):
        """must_be_open_source=True forces budget to 'low' in raw constraints."""
        ctx = make_recommendation_context(budget="enterprise", must_be_open_source=True)
        raw = ctx.to_raw_constraints()
        assert raw["budget"] == "low"

    def test_recommendation_context_no_cloud_preference(self):
        """cloud_preference='none' defaults to local-docker in raw constraints."""
        ctx = make_recommendation_context(cloud_preference="none")
        raw = ctx.to_raw_constraints()
        assert raw["cloud_provider"] == "local-docker"

    def test_recommendation_context_deployment_preference_overrides(self):
        """explicit deployment_preference overrides budget default."""
        ctx = make_recommendation_context(
            budget="low",
            deployment_preference="kubernetes"
        )
        raw = ctx.to_raw_constraints()
        assert raw["deployment"] == "kubernetes"
        assert raw["iac"] == "helm"

    def test_recommendation_context_managed_deployment(self):
        """managed deployment preference maps to terraform iac."""
        ctx = make_recommendation_context(deployment_preference="managed")
        raw = ctx.to_raw_constraints()
        assert raw["deployment"] == "managed"
        assert raw["iac"] == "terraform"
