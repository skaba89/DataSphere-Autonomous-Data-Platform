"""Tests des deux modes de la plateforme."""
import json
import pytest
from pathlib import Path

from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.agents.mode_router import run_explicit, run_recommended
from datasphere.agents.proposer import generate_proposals, _apply_team_scoring


# ─────────────────────────────────────────────────────────────────────────────
# Mode 1 — Explicit Stack
# ─────────────────────────────────────────────────────────────────────────────

class TestMode1ExplicitStack:

    def _stack(self, **kwargs) -> ExplicitStack:
        defaults = dict(
            business_request="Analyse les ventes",
            cloud_provider="aws",
            data_warehouse="snowflake",
            orchestrator="airflow",
            ingestion="airbyte",
            transformation="dbt",
            bi_tool="superset",
            deployment="kubernetes",
            security=["RBAC", "Vault"],
            budget="enterprise",
        )
        defaults.update(kwargs)
        return ExplicitStack(**defaults)

    def test_explicit_stack_generates_artifacts(self, tmp_path):
        stack = self._stack()
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.success
        assert result.stack_advisor is not None
        assert result.infrastructure is not None

    def test_explicit_stack_local_docker(self, tmp_path):
        stack = self._stack(
            cloud_provider="local-docker",
            data_warehouse="postgresql",
            orchestrator="dagster",
            ingestion="meltano",
            transformation="sqlmesh",
            bi_tool="metabase",
            deployment="docker-compose",
            budget="low",
        )
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.success
        # Should generate docker-compose
        assert any(
            "docker-compose.yml" in (out.artifacts or {})
            for out in [result.infrastructure] if out
        )

    def test_explicit_stack_preserves_tool_choices(self, tmp_path):
        stack = self._stack(data_warehouse="clickhouse", orchestrator="prefect")
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        validated = result.stack_advisor.validated_stack
        assert validated["warehouse"] == "clickhouse"
        assert validated["orchestration"] == "prefect"

    def test_explicit_stack_to_constraints_conversion(self):
        stack = self._stack(data_lake="s3", catalog="openmetadata", quality="great-expectations")
        constraints = stack.to_architecture_constraints()
        assert constraints.cloud_provider == "aws"
        assert constraints.data_warehouse == "snowflake"
        assert constraints.data_lake == "s3"
        assert constraints.catalog == "openmetadata"

    def test_mode1_json_examples(self, tmp_path):
        for f in Path("examples").glob("mode1_*.json"):
            data = json.loads(f.read_text())
            stack = ExplicitStack(**{k: v for k, v in data.items() if k != "mode"})
            result = run_explicit(stack, output_dir=str(tmp_path / f.stem), verbose=False)
            assert result.success, f"Mode 1 failed for {f.name}"

    def test_explicit_stack_security_rls_generated(self, tmp_path):
        stack = self._stack(security=["RBAC", "RLS", "Vault"])
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        rls = result.security_compliance.rls_policies
        assert len(rls) > 0

    def test_explicit_stack_github_actions_generated(self, tmp_path):
        stack = self._stack()
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert ".github/workflows/deploy.yml" in result.deployment.artifacts

    def test_explicit_stack_cost_report_generated(self, tmp_path):
        stack = self._stack()
        result = run_explicit(stack, output_dir=str(tmp_path), verbose=False)
        assert result.cost_optimization.total_monthly_usd > 0
        assert "cost_report.md" in result.cost_optimization.artifacts


# ─────────────────────────────────────────────────────────────────────────────
# Mode 2 — Recommendation Context
# ─────────────────────────────────────────────────────────────────────────────

class TestMode2RecommendedStack:

    def _ctx(self, **kwargs) -> RecommendationContext:
        defaults = dict(
            business_request="Analyse les données",
            budget="medium",
            data_volume="medium",
            security_level="rbac",
            team_size="small",
            processing_mode="batch",
            cloud_preference="none",
        )
        defaults.update(kwargs)
        return RecommendationContext(**defaults)

    def test_recommended_generates_artifacts(self, tmp_path):
        ctx = self._ctx()
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.success

    def test_open_source_constraint_filters_saas(self, tmp_path):
        ctx = self._ctx(must_be_open_source=True, budget="low")
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        proposals = _apply_team_scoring(proposals, ctx)
        saas = {"snowflake", "databricks", "tableau", "powerbi", "fivetran-like"}
        for p in proposals:
            wh = p.constraints.data_warehouse
            bi = p.constraints.bi_tool
            assert wh not in saas, f"Open-source constraint violated: warehouse={wh}"
            assert bi not in saas, f"Open-source constraint violated: bi={bi}"

    def test_team_solo_prefers_low_complexity(self, tmp_path):
        ctx = self._ctx(team_size="solo", budget="low")
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        proposals = _apply_team_scoring(proposals, ctx)
        # First proposal should be low or medium complexity for solo
        assert proposals[0].complexity in ("low", "medium")

    def test_team_large_allows_high_complexity(self, tmp_path):
        ctx = self._ctx(team_size="large", budget="enterprise", cloud_preference="aws")
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        proposals = _apply_team_scoring(proposals, ctx)
        complexities = [p.complexity for p in proposals]
        assert "high" in complexities

    def test_existing_tools_bonus_applied(self):
        ctx = self._ctx(
            existing_tools=["airflow", "postgresql"],
            cloud_preference="local-docker",
        )
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        proposals = _apply_team_scoring(proposals, ctx)
        # At least one proposal should mention existing tools in pros
        all_pros = [pro for p in proposals for pro in p.pros]
        assert any("existant" in pro.lower() or "airflow" in pro.lower() or "postgresql" in pro.lower()
                   for pro in all_pros)

    def test_compliance_hds_prefers_local_infra(self):
        ctx = self._ctx(
            compliance_requirements=["HDS"],
            cloud_preference="none",
            security_level="enterprise",
        )
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        proposals = _apply_team_scoring(proposals, ctx)
        all_pros = [pro for p in proposals for pro in p.pros]
        assert any("HDS" in pro or "HIPAA" in pro or "hébergée" in pro.lower()
                   for pro in all_pros)

    def test_realtime_mode_triggers_streaming_proposal(self):
        ctx = self._ctx(processing_mode="realtime")
        raw = ctx.to_raw_constraints()
        proposals = generate_proposals(raw)
        names = [p.name.lower() for p in proposals]
        assert any("streaming" in n or "temps réel" in n for n in names)

    def test_context_to_raw_constraints(self):
        ctx = self._ctx(
            cloud_preference="gcp",
            deployment_preference="kubernetes",
            security_level="enterprise",
        )
        raw = ctx.to_raw_constraints()
        assert raw["cloud_provider"] == "gcp"
        assert raw["deployment"] == "kubernetes"
        assert "Vault" in raw["security"]

    def test_mode2_json_examples(self, tmp_path):
        for f in Path("examples").glob("mode2_*.json"):
            data = json.loads(f.read_text())
            ctx = RecommendationContext(**{k: v for k, v in data.items() if k != "mode"})
            result = run_recommended(ctx, output_dir=str(tmp_path / f.stem), verbose=False)
            assert result.success, f"Mode 2 failed for {f.name}"

    def test_healthcare_enterprise_azure(self, tmp_path):
        ctx = RecommendationContext(
            business_request="Plateforme analytique données de santé — 15 hôpitaux",
            budget="enterprise",
            data_volume="large",
            security_level="enterprise",
            team_size="large",
            processing_mode="batch",
            cloud_preference="azure",
            deployment_preference="kubernetes",
            must_be_open_source=False,
            existing_tools=["postgresql", "airflow"],
            compliance_requirements=["HDS", "RGPD"],
        )
        result = run_recommended(ctx, output_dir=str(tmp_path), verbose=False)
        assert result.success
        assert result.security_compliance is not None
        notes = result.security_compliance.compliance_notes
        assert any("HDS" in n or "santé" in n.lower() for n in notes)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy JSON format backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyFormat:
    def test_legacy_request_format_still_works(self, tmp_path):
        """Old BusinessRequest format should still be accepted via _legacy_to_explicit."""
        from datasphere.cli.run_agents import _legacy_to_explicit
        from datasphere.models.modes import ExplicitStack

        legacy = {
            "business_request": "Analyse les ventes",
            "architecture_constraints": {
                "cloud_provider": "aws",
                "data_warehouse": "snowflake",
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt Core",
                "data_lake": "S3",
                "bi_tool": "superset",
                "catalog": "openmetadata",
                "quality": "great-expectations",
                "deployment": "kubernetes",
                "iac": "terraform",
                "security": ["RBAC", "Vault", "RLS"],
            }
        }
        converted = _legacy_to_explicit(legacy)
        stack = ExplicitStack(**{k: v for k, v in converted.items() if k != "mode"})
        assert stack.data_warehouse == "snowflake"
        assert stack.cloud_provider == "aws"

    def test_legacy_json_example_files(self, tmp_path):
        from datasphere.cli.run_agents import _legacy_to_explicit
        from datasphere.models.modes import ExplicitStack
        from datasphere.agents.mode_router import run_explicit

        for f in Path("examples").glob("request_*.json"):
            data = json.loads(f.read_text())
            converted = _legacy_to_explicit(data)
            stack = ExplicitStack(**{k: v for k, v in converted.items() if k != "mode"})
            result = run_explicit(stack, output_dir=str(tmp_path / f.stem), verbose=False)
            assert result.success, f"Legacy format failed for {f.name}"
