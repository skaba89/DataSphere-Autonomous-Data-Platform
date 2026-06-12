"""Tests for cost_tables.py — pricing tables and CostCalculator."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from datasphere.agents.cost_tables import (
    SNOWFLAKE_COSTS,
    BIGQUERY_COSTS,
    INGESTION_COSTS,
    BI_COSTS,
    CLOUD_BASE_COSTS,
    CostCalculator,
)


# ---------------------------------------------------------------------------
# Pricing table sanity checks
# ---------------------------------------------------------------------------

def test_snowflake_medium_cost_reasonable():
    cost = SNOWFLAKE_COSTS["medium"]
    assert 200 <= cost <= 2000, f"Snowflake medium cost {cost} outside expected range"


def test_bigquery_low_cost_positive():
    cost = BIGQUERY_COSTS["low"]
    assert cost > 0, "BigQuery low cost should be positive"


def test_fivetran_more_expensive_than_airbyte():
    for tier in ("low", "medium", "enterprise"):
        fivetran = INGESTION_COSTS["fivetran"][tier]
        airbyte = INGESTION_COSTS["airbyte"][tier]
        assert fivetran >= airbyte, f"Fivetran should be >= Airbyte at tier={tier}"


def test_tableau_more_expensive_than_metabase():
    for tier in ("low", "medium", "enterprise"):
        tableau = BI_COSTS["tableau"][tier]
        metabase = BI_COSTS["metabase"][tier]
        assert tableau >= metabase, f"Tableau should be >= Metabase at tier={tier}"


# ---------------------------------------------------------------------------
# CostCalculator
# ---------------------------------------------------------------------------

SAMPLE_STACK = {
    "cloud_provider": "aws",
    "data_warehouse": "snowflake",
    "orchestrator": "airflow",
    "ingestion": "fivetran",
    "transformation": "dbt",
    "bi_tool": "tableau",
    "quality": "great-expectations",
    "catalog": "datahub",
}


def test_calculator_returns_breakdown_with_line_items():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    assert len(bd.line_items) > 0, "Should return at least one line item"


def test_calculator_total_is_sum_of_line_items():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    total_from_items = round(sum(item.monthly_usd for item in bd.line_items), 2)
    assert abs(bd.total_monthly_usd - total_from_items) < 0.01, (
        f"total_monthly_usd={bd.total_monthly_usd} != sum of items={total_from_items}"
    )


def test_calculator_comparison_has_all_clouds():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    assert "aws" in bd.comparison
    assert "gcp" in bd.comparison
    assert "azure" in bd.comparison


def test_savings_tips_suggest_airbyte_when_fivetran():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    tips_text = " ".join(bd.savings_tips).lower()
    assert "airbyte" in tips_text, "Should suggest Airbyte as alternative to Fivetran"


def test_savings_tips_suggest_metabase_when_tableau():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    tips_text = " ".join(bd.savings_tips).lower()
    assert any(alt in tips_text for alt in ("metabase", "superset")), (
        "Should suggest a cheaper BI alternative when Tableau is used"
    )


def test_aws_stack_total_positive():
    calc = CostCalculator()
    bd = calc.calculate({"cloud_provider": "aws", "data_warehouse": "snowflake"}, "medium")
    assert bd.total_monthly_usd > 0


def test_gcp_stack_total_positive():
    calc = CostCalculator()
    bd = calc.calculate({"cloud_provider": "gcp", "data_warehouse": "bigquery"}, "medium")
    assert bd.total_monthly_usd > 0


def test_yearly_is_12x_monthly():
    calc = CostCalculator()
    bd = calc.calculate(SAMPLE_STACK, "medium")
    assert abs(bd.total_yearly_usd - bd.total_monthly_usd * 12) < 0.1


def test_api_cost_estimate_endpoint():
    from datasphere.api.app import create_app
    client = TestClient(create_app())
    resp = client.post("/costs/estimate", json={"stack": SAMPLE_STACK, "budget": "medium"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_monthly_usd" in data
    assert "line_items" in data
    assert "comparison" in data
    assert "savings_tips" in data


def test_enterprise_costs_more_than_low():
    calc = CostCalculator()
    low = calc.calculate(SAMPLE_STACK, "low").total_monthly_usd
    enterprise = calc.calculate(SAMPLE_STACK, "enterprise").total_monthly_usd
    assert enterprise > low, "Enterprise tier should cost more than low tier"


def test_unknown_tool_defaults_gracefully():
    """No KeyError when the stack contains unknown tool names."""
    calc = CostCalculator()
    stack = {
        "cloud_provider": "aws",
        "data_warehouse": "unknown_warehouse_xyz",
        "ingestion": "unknown_ingestion_xyz",
        "orchestrator": "unknown_orch_xyz",
        "bi_tool": "unknown_bi_xyz",
    }
    # Should not raise
    bd = calc.calculate(stack, "medium")
    assert bd.total_monthly_usd >= 0
