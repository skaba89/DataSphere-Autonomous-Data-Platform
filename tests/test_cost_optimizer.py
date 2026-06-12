"""Tests for CostOptimizer and POST /costs/optimize endpoint."""
import pytest
from datasphere.agents.cost_optimizer import CostOptimizer, CostOptimizationReport


SNOWFLAKE_STACK = {
    "data_warehouse": "snowflake",
    "orchestrator": "airflow",
    "ingestion": "fivetran",
}

MONTHLY_COSTS = {
    "data_warehouse": 800.0,
    "orchestrator": 150.0,
    "ingestion": 200.0,
}


def test_analyze_returns_report():
    optimizer = CostOptimizer()
    report = optimizer.analyze(SNOWFLAKE_STACK, MONTHLY_COSTS)
    assert isinstance(report, CostOptimizationReport)


def test_snowflake_generates_1yr_reservation():
    optimizer = CostOptimizer()
    report = optimizer.analyze(SNOWFLAKE_STACK, MONTHLY_COSTS)
    recs = [r for r in report.reserved_instance_recommendations if r.current_tool == "snowflake"]
    assert len(recs) >= 1
    assert recs[0].commitment_term == "1yr"
    assert recs[0].savings_pct > 0
    assert recs[0].annual_savings_usd > 0


def test_optimized_less_than_current():
    optimizer = CostOptimizer()
    report = optimizer.analyze(SNOWFLAKE_STACK, MONTHLY_COSTS)
    assert report.total_optimized_monthly_usd < report.total_current_monthly_usd


def test_optimization_score_range():
    optimizer = CostOptimizer()
    report = optimizer.analyze(SNOWFLAKE_STACK, MONTHLY_COSTS)
    assert 0 <= report.optimization_score <= 100


def test_no_reservations_for_empty_stack():
    optimizer = CostOptimizer()
    report = optimizer.analyze({}, {})
    assert report.reserved_instance_recommendations == []
    assert report.total_current_monthly_usd == 0.0
    assert report.total_optimized_monthly_usd == 0.0


def test_optimize_costs_endpoint(client):
    resp = client.post("/costs/optimize", json={
        "stack": {"data_warehouse": "snowflake", "orchestrator": "airflow"},
        "budget": "medium",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "current_monthly_usd" in data
    assert "optimized_monthly_usd" in data
    assert "annual_savings_usd" in data
    assert "optimization_score" in data
    assert "reserved_instance_recommendations" in data
    assert "quick_wins" in data
    assert "medium_term" in data
    assert "long_term" in data


def test_optimize_costs_endpoint_score_range(client):
    resp = client.post("/costs/optimize", json={
        "stack": {"data_warehouse": "redshift"},
        "budget": "low",
    })
    assert resp.status_code == 200
    score = resp.json()["optimization_score"]
    assert 0 <= score <= 100
