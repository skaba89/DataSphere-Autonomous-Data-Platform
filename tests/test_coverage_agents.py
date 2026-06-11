"""
Targeted tests for agent edge cases:
- base_agent error handling
- mode_router run_explicit / run_recommended
- cost_tables data
- stack_advisor edge cases
- orchestrator
"""
from __future__ import annotations

import pytest

from datasphere.agents.base_agent import BaseAgent
from datasphere.models.output import AgentOutput
from datasphere.models.request import BusinessRequest, ArchitectureConstraints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_constraints(**overrides) -> ArchitectureConstraints:
    defaults = dict(
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="metabase",
        deployment="docker-compose",
    )
    defaults.update(overrides)
    return ArchitectureConstraints(**defaults)


def _make_request(**overrides) -> BusinessRequest:
    constraints = overrides.pop("constraints", _make_constraints())
    return BusinessRequest(
        business_request=overrides.pop("business_request", "Test pipeline"),
        architecture_constraints=constraints,
    )


# ---------------------------------------------------------------------------
# BaseAgent — error handling
# ---------------------------------------------------------------------------

class TestBaseAgentErrorHandling:
    def test_run_catches_exception_returns_failed_output(self):
        class BrokenAgent(BaseAgent):
            name = "broken"

            def _run(self, request, context):
                raise ValueError("intentional error")

        agent = BrokenAgent()
        req = _make_request()
        result = agent.run(req)
        assert result.success is False
        assert any("ValueError" in e for e in result.errors)

    def test_run_with_no_context_uses_empty_dict(self):
        class OkAgent(BaseAgent):
            name = "ok"

            def _run(self, request, context):
                assert isinstance(context, dict)
                return AgentOutput(agent="ok", success=True)

        agent = OkAgent()
        req = _make_request()
        result = agent.run(req)
        assert result.success is True

    def test_run_passes_context_to_implementation(self):
        class ContextAgent(BaseAgent):
            name = "ctx"

            def _run(self, request, context):
                return AgentOutput(agent="ctx", success=True, metadata={"ctx_keys": list(context.keys())})

        agent = ContextAgent()
        req = _make_request()
        mock_context = {"prev": AgentOutput(agent="prev", success=True)}
        result = agent.run(req, context=mock_context)
        assert result.success is True
        assert "prev" in result.metadata.get("ctx_keys", [])


# ---------------------------------------------------------------------------
# cost_tables — basic data integrity
# ---------------------------------------------------------------------------

class TestCostTables:
    def test_aws_warehouse_costs_have_expected_warehouses(self):
        from datasphere.agents.cost_tables import AWS_WAREHOUSE_COSTS
        assert "redshift" in AWS_WAREHOUSE_COSTS
        assert "postgresql" in AWS_WAREHOUSE_COSTS
        for wh, tiers in AWS_WAREHOUSE_COSTS.items():
            assert "low" in tiers
            assert "medium" in tiers
            assert "enterprise" in tiers

    def test_snowflake_costs_by_tier(self):
        from datasphere.agents.cost_tables import SNOWFLAKE_COSTS
        assert SNOWFLAKE_COSTS["low"] < SNOWFLAKE_COSTS["medium"]
        assert SNOWFLAKE_COSTS["medium"] < SNOWFLAKE_COSTS["enterprise"]

    def test_bigquery_costs_exist(self):
        from datasphere.agents.cost_tables import BIGQUERY_COSTS
        assert BIGQUERY_COSTS["enterprise"] > 0

    def test_duckdb_costs_are_zero(self):
        from datasphere.agents.cost_tables import DUCKDB_COSTS
        for tier, cost in DUCKDB_COSTS.items():
            assert cost == 0

    def test_orchestration_costs_have_airflow(self):
        from datasphere.agents.cost_tables import ORCHESTRATION_COSTS
        assert "airflow" in ORCHESTRATION_COSTS
        assert "low" in ORCHESTRATION_COSTS["airflow"]

    def test_synapse_costs_exist(self):
        from datasphere.agents.cost_tables import SYNAPSE_COSTS
        assert SYNAPSE_COSTS["medium"] > 0

    def test_databricks_costs_exist(self):
        from datasphere.agents.cost_tables import DATABRICKS_COSTS
        assert DATABRICKS_COSTS["enterprise"] > 0

    def test_clickhouse_low_is_zero(self):
        from datasphere.agents.cost_tables import CLICKHOUSE_COSTS
        assert CLICKHOUSE_COSTS["low"] == 0


# ---------------------------------------------------------------------------
# Mode Router — run_explicit / run_recommended
# ---------------------------------------------------------------------------

class TestModeRouter:
    def test_run_explicit_returns_output(self):
        from datasphere.models.modes import ExplicitStack
        from datasphere.agents.mode_router import run_explicit

        stack = ExplicitStack(
            business_request="Test analytics",
            cloud_provider="aws",
            data_warehouse="snowflake",
            orchestrator="airflow",
            ingestion="airbyte",
            transformation="dbt",
            bi_tool="metabase",
            deployment="docker-compose",
            budget="medium",
            data_volume="small",
        )
        result = run_explicit(stack, output_dir=None, verbose=False)
        assert result is not None
        assert hasattr(result, "success")

    def test_run_explicit_verbose_false(self):
        from datasphere.models.modes import ExplicitStack
        from datasphere.agents.mode_router import run_explicit

        stack = ExplicitStack(
            business_request="Pipeline ventes",
            cloud_provider="gcp",
            data_warehouse="bigquery",
            orchestrator="dagster",
            ingestion="meltano",
            transformation="dbt",
            bi_tool="superset",
            deployment="kubernetes",
            budget="low",
            data_volume="small",
        )
        result = run_explicit(stack, output_dir=None, verbose=False)
        assert result is not None

    def test_run_recommended_returns_output(self):
        from datasphere.models.modes import RecommendationContext
        from datasphere.agents.mode_router import run_recommended

        ctx = RecommendationContext(
            business_request="Analyse des données logistiques",
            budget="medium",
            data_volume="small",
            security_level="simple",
            team_size="small",
            processing_mode="batch",
            cloud_preference="aws",
            must_be_open_source=False,
        )
        result = run_recommended(ctx, output_dir=None, verbose=False)
        assert result is not None
        assert hasattr(result, "success")

    def test_run_recommended_open_source(self):
        from datasphere.models.modes import RecommendationContext
        from datasphere.agents.mode_router import run_recommended

        ctx = RecommendationContext(
            business_request="Open source analytics platform",
            budget="low",
            data_volume="small",
            security_level="simple",
            team_size="solo",
            processing_mode="batch",
            cloud_preference="local-docker",
            must_be_open_source=True,
        )
        result = run_recommended(ctx, output_dir=None, verbose=False)
        assert result is not None

    def test_print_mode1_summary_runs(self):
        from datasphere.models.modes import ExplicitStack
        from datasphere.agents.mode_router import _print_mode1_summary

        stack = ExplicitStack(
            business_request="Test",
            cloud_provider="aws",
            data_warehouse="snowflake",
            orchestrator="airflow",
            ingestion="airbyte",
            transformation="dbt",
            bi_tool="metabase",
            deployment="docker-compose",
        )
        # Should not raise
        _print_mode1_summary(stack)

    def test_print_mode2_context_runs(self):
        from datasphere.models.modes import RecommendationContext
        from datasphere.agents.mode_router import _print_mode2_context

        ctx = RecommendationContext(
            business_request="Analytics platform",
            budget="medium",
            data_volume="medium",
            security_level="rbac",
            team_size="medium",
            processing_mode="batch",
            cloud_preference="none",
            must_be_open_source=False,
            existing_tools=["airflow"],
            compliance_requirements=["RGPD"],
        )
        # Should not raise
        _print_mode2_context(ctx)


# ---------------------------------------------------------------------------
# Stack Advisor edge cases
# ---------------------------------------------------------------------------

class TestStackAdvisorEdgeCases:
    def test_minimal_stack_passes_validation(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent

        agent = StackAdvisorAgent()
        req = _make_request(constraints=_make_constraints(
            data_warehouse="duckdb",
            deployment="docker-compose",
            budget="low",
        ))
        result = agent.run(req)
        assert result is not None
        assert hasattr(result, "success")

    def test_azure_synapse_stack(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent

        agent = StackAdvisorAgent()
        req = _make_request(constraints=_make_constraints(
            cloud_provider="azure",
            data_warehouse="azure-synapse",
            deployment="kubernetes",
        ))
        result = agent.run(req)
        assert result is not None

    def test_gcp_bigquery_stack(self):
        from datasphere.agents.stack_advisor import StackAdvisorAgent

        agent = StackAdvisorAgent()
        req = _make_request(constraints=_make_constraints(
            cloud_provider="gcp",
            data_warehouse="bigquery",
            orchestrator="dagster",
        ))
        result = agent.run(req)
        assert result is not None


# ---------------------------------------------------------------------------
# Cloud Architect edge cases
# ---------------------------------------------------------------------------

class TestCloudArchitectEdgeCases:
    def test_local_docker_stack(self):
        from datasphere.agents.cloud_architect import CloudArchitectAgent

        agent = CloudArchitectAgent()
        req = _make_request(constraints=_make_constraints(
            cloud_provider="local-docker",
            data_warehouse="postgresql",
            deployment="docker-compose",
        ))
        result = agent.run(req)
        assert result is not None

    def test_on_premise_stack(self):
        from datasphere.agents.cloud_architect import CloudArchitectAgent

        agent = CloudArchitectAgent()
        req = _make_request(constraints=_make_constraints(
            cloud_provider="on-premise",
            data_warehouse="clickhouse",
            deployment="kubernetes",
        ))
        result = agent.run(req)
        assert result is not None


# ---------------------------------------------------------------------------
# Cost Optimization edge cases
# ---------------------------------------------------------------------------

class TestCostOptimizationEdgeCases:
    def test_low_budget_stack(self):
        from datasphere.agents.cost_optimization import CostOptimizationAgent

        agent = CostOptimizationAgent()
        req = _make_request(constraints=_make_constraints(
            data_warehouse="duckdb",
            budget="low",
        ))
        result = agent.run(req)
        assert result.success is True

    def test_enterprise_budget_stack(self):
        from datasphere.agents.cost_optimization import CostOptimizationAgent

        agent = CostOptimizationAgent()
        req = _make_request(constraints=_make_constraints(
            data_warehouse="snowflake",
            budget="enterprise",
        ))
        result = agent.run(req)
        assert result.success is True
        assert result.metadata.get("total_monthly_usd", 0) > 0


# ---------------------------------------------------------------------------
# Security Compliance edge cases
# ---------------------------------------------------------------------------

class TestSecurityComplianceEdgeCases:
    def test_enterprise_security(self):
        from datasphere.agents.security_compliance import SecurityComplianceAgent

        agent = SecurityComplianceAgent()
        req = _make_request(constraints=_make_constraints(
            security=["RBAC", "RLS", "Vault"],
        ))
        result = agent.run(req)
        assert result.success is True

    def test_minimal_security(self):
        from datasphere.agents.security_compliance import SecurityComplianceAgent

        agent = SecurityComplianceAgent()
        req = _make_request(constraints=_make_constraints(
            security=[],
        ))
        result = agent.run(req)
        assert result is not None


# ---------------------------------------------------------------------------
# Deployment Agent edge cases
# ---------------------------------------------------------------------------

class TestDeploymentEdgeCases:
    def test_kubernetes_deployment(self):
        from datasphere.agents.deployment import DeploymentAgent

        agent = DeploymentAgent()
        req = _make_request(constraints=_make_constraints(
            deployment="kubernetes",
        ))
        result = agent.run(req)
        assert result is not None

    def test_docker_compose_deployment(self):
        from datasphere.agents.deployment import DeploymentAgent

        agent = DeploymentAgent()
        req = _make_request(constraints=_make_constraints(
            deployment="docker-compose",
        ))
        result = agent.run(req)
        assert result is not None
