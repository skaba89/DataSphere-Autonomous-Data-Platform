"""Tests for the LineageGenerator and /lineage/generate API endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from datasphere.generators.lineage import LineageGenerator, LineageOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_STACK = {
    "cloud_provider": "aws",
    "data_warehouse": "snowflake",
    "orchestrator": "airflow",
    "ingestion": "airbyte",
    "transformation": "dbt",
    "bi_tool": "metabase",
    "deployment": "kubernetes",
}


@pytest.fixture
def gen():
    return LineageGenerator()


@pytest.fixture
def output(gen):
    return gen.generate(BASE_STACK, "Test pipeline")


# ---------------------------------------------------------------------------
# 1. Basic generation returns a LineageOutput
# ---------------------------------------------------------------------------

def test_basic_generation_returns_lineage_output(gen):
    result = gen.generate(BASE_STACK)
    assert isinstance(result, LineageOutput)
    assert result.mermaid
    assert result.nodes
    assert result.edges
    assert result.format == "mermaid"


# ---------------------------------------------------------------------------
# 2. Mermaid starts with flowchart LR
# ---------------------------------------------------------------------------

def test_mermaid_starts_with_flowchart(output):
    assert output.mermaid.startswith("flowchart LR")


# ---------------------------------------------------------------------------
# 3. Source node present
# ---------------------------------------------------------------------------

def test_mermaid_has_source_node(output):
    assert "Source Systems" in output.mermaid


# ---------------------------------------------------------------------------
# 4. Ingestion node present for known tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,label", [
    ("airbyte", "Airbyte"),
    ("meltano", "Meltano"),
    ("fivetran", "Fivetran"),
])
def test_mermaid_has_ingestion_node(gen, tool, label):
    stack = {**BASE_STACK, "ingestion": tool}
    result = gen.generate(stack)
    assert label in result.mermaid


# ---------------------------------------------------------------------------
# 5. Warehouse node present for known tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,label", [
    ("snowflake", "Snowflake"),
    ("bigquery", "BigQuery"),
    ("postgresql", "PostgreSQL"),
])
def test_mermaid_has_warehouse_node(gen, tool, label):
    stack = {**BASE_STACK, "data_warehouse": tool}
    result = gen.generate(stack)
    assert label in result.mermaid


# ---------------------------------------------------------------------------
# 6. Transformation node present
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,label", [
    ("dbt", "dbt Core"),
    ("spark", "Apache Spark"),
])
def test_mermaid_has_transform_node(gen, tool, label):
    stack = {**BASE_STACK, "transformation": tool}
    result = gen.generate(stack)
    assert label in result.mermaid


# ---------------------------------------------------------------------------
# 7. BI node present for known tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,label", [
    ("metabase", "Metabase"),
    ("superset", "Apache Superset"),
])
def test_mermaid_has_bi_node(gen, tool, label):
    stack = {**BASE_STACK, "bi_tool": tool}
    result = gen.generate(stack)
    assert label in result.mermaid


# ---------------------------------------------------------------------------
# 8. Orchestrator dotted edge appears
# ---------------------------------------------------------------------------

def test_mermaid_has_orchestrator_dotted_edge(output):
    assert "-.->|" in output.mermaid
    assert "schedules" in output.mermaid


# ---------------------------------------------------------------------------
# 9. Quality node appears when set
# ---------------------------------------------------------------------------

def test_mermaid_has_quality_node_when_set(gen):
    stack = {**BASE_STACK, "quality": "great-expectations"}
    result = gen.generate(stack)
    assert "Great Expectations" in result.mermaid
    assert any("quality" in str(e) for e in result.edges)


# ---------------------------------------------------------------------------
# 10. Catalog node appears when set
# ---------------------------------------------------------------------------

def test_mermaid_has_catalog_node_when_set(gen):
    stack = {**BASE_STACK, "catalog": "datahub"}
    result = gen.generate(stack)
    assert "DataHub" in result.mermaid
    assert any("catalog" in str(e) for e in result.edges)


# ---------------------------------------------------------------------------
# 11. Output has a nodes list
# ---------------------------------------------------------------------------

def test_output_has_nodes_list(output):
    assert isinstance(output.nodes, list)
    assert len(output.nodes) >= 6  # src, ingest, raw, transform, serving, bi, orch
    # node names are display strings
    assert any("Snowflake" in n for n in output.nodes)
    assert any("Airbyte" in n for n in output.nodes)


# ---------------------------------------------------------------------------
# 12. API /lineage/generate endpoint
# ---------------------------------------------------------------------------

def test_api_lineage_endpoint():
    from datasphere.api.app import create_app
    client = TestClient(create_app())
    resp = client.post("/lineage/generate", json={"stack": BASE_STACK, "business_request": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "mermaid" in data
    assert data["mermaid"].startswith("flowchart LR")
    assert "nodes" in data
    assert "edge_count" in data
    assert data["edge_count"] > 0
    assert "embed_url" in data
    assert "mermaid.live" in data["embed_url"]
