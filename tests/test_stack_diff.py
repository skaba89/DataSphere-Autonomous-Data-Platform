"""Tests for StackDiffGenerator and /stacks/diff API endpoint."""
import pytest
from datasphere.generators.stack_diff import StackDiffGenerator, MigrationPlan, StackChange


@pytest.fixture
def gen():
    return StackDiffGenerator()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_no_change_returns_empty_changes(gen):
    stack = {"data_warehouse": "snowflake", "orchestrator": "airflow"}
    plan = gen.diff(stack, stack)
    assert plan.changes == []


def test_airflow_to_dagster_is_high_effort(gen):
    plan = gen.diff({"orchestrator": "airflow"}, {"orchestrator": "dagster"})
    change = next(c for c in plan.changes if c.component == "orchestrator")
    assert change.effort == "high"


def test_redshift_to_snowflake_migration_has_steps(gen):
    plan = gen.diff({"data_warehouse": "redshift"}, {"data_warehouse": "snowflake"})
    change = next(c for c in plan.changes if c.component == "data_warehouse")
    assert len(change.migration_steps) >= 5


def test_redshift_to_snowflake_days_gt_20(gen):
    plan = gen.diff({"data_warehouse": "redshift"}, {"data_warehouse": "snowflake"})
    change = next(c for c in plan.changes if c.component == "data_warehouse")
    assert change.estimated_days > 20


def test_fivetran_to_airbyte_saves_cost(gen):
    plan = gen.diff({"ingestion": "fivetran"}, {"ingestion": "airbyte"})
    change = next(c for c in plan.changes if c.component == "ingestion")
    assert any("Cancel Fivetran" in step for step in change.migration_steps)


def test_migration_order_warehouse_before_orchestrator(gen):
    from_stack = {"data_warehouse": "redshift", "orchestrator": "airflow"}
    to_stack = {"data_warehouse": "snowflake", "orchestrator": "dagster"}
    plan = gen.diff(from_stack, to_stack)
    order = plan.migration_order
    assert order.index("data_warehouse") < order.index("orchestrator")


def test_overall_risk_high_when_any_high(gen):
    # redshift→snowflake is high risk
    from_stack = {"data_warehouse": "redshift", "ingestion": "fivetran"}
    to_stack = {"data_warehouse": "snowflake", "ingestion": "airbyte"}
    plan = gen.diff(from_stack, to_stack)
    assert plan.overall_risk == "high"


def test_overall_risk_low_when_all_low(gen):
    # airbyte→fivetran is low/low, metabase→superset is low/low
    from_stack = {"ingestion": "airbyte", "bi_tool": "metabase"}
    to_stack = {"ingestion": "fivetran", "bi_tool": "superset"}
    plan = gen.diff(from_stack, to_stack)
    assert plan.overall_risk == "low"


def test_total_days_is_sum_of_changes(gen):
    from_stack = {"data_warehouse": "redshift", "orchestrator": "airflow"}
    to_stack = {"data_warehouse": "snowflake", "orchestrator": "dagster"}
    plan = gen.diff(from_stack, to_stack)
    expected = sum(c.estimated_days for c in plan.changes)
    assert plan.total_estimated_days == expected


def test_rollback_strategy_not_empty(gen):
    plan = gen.diff({"orchestrator": "airflow"}, {"orchestrator": "dagster"})
    assert plan.rollback_strategy and len(plan.rollback_strategy) > 10


def test_summary_mentions_both_tools(gen):
    plan = gen.diff({"data_warehouse": "redshift"}, {"data_warehouse": "snowflake"})
    summary_lower = plan.summary.lower()
    assert "redshift" in summary_lower
    assert "snowflake" in summary_lower


def test_add_change_when_component_only_in_to(gen):
    plan = gen.diff({}, {"orchestrator": "dagster"})
    change = next(c for c in plan.changes if c.component == "orchestrator")
    assert change.change_type == "add"
    assert change.to_tool == "dagster"
    assert change.from_tool == ""


def test_remove_change_when_component_only_in_from(gen):
    plan = gen.diff({"bi_tool": "tableau"}, {})
    change = next(c for c in plan.changes if c.component == "bi_tool")
    assert change.change_type == "remove"
    assert change.from_tool == "tableau"
    assert change.to_tool == ""


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_api_stack_diff_endpoint():
    from fastapi.testclient import TestClient
    from datasphere.api.app import app
    client = TestClient(app)
    payload = {
        "from_stack": {"data_warehouse": "redshift", "orchestrator": "airflow"},
        "to_stack": {"data_warehouse": "snowflake", "orchestrator": "dagster"},
    }
    res = client.post("/stacks/diff", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "changes" in data
    assert isinstance(data["changes"], list)
    assert data["total_estimated_days"] > 0
    assert data["overall_risk"] in ("low", "medium", "high")


def test_identical_stacks_returns_no_changes_via_api():
    from fastapi.testclient import TestClient
    from datasphere.api.app import app
    client = TestClient(app)
    stack = {"data_warehouse": "snowflake", "orchestrator": "airflow"}
    payload = {"from_stack": stack, "to_stack": stack}
    res = client.post("/stacks/diff", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["changes"] == []
    assert data["total_estimated_days"] == 0
