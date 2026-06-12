"""Tests for datasphere.plugins — PluginRegistry and GET /plugins endpoint."""
from __future__ import annotations

import pytest
from datasphere.plugins import GeneratorPlugin, PluginRegistry, plugin_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_registry() -> PluginRegistry:
    """Return a new, unloaded registry (isolated from the module singleton)."""
    return PluginRegistry()


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

def test_registry_loads_builtins():
    reg = _fresh_registry()
    reg.load()
    assert len(reg.list_all()) >= 6


def test_registry_get_dbt():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("dbt")
    assert plugin is not None
    assert isinstance(plugin, GeneratorPlugin)
    assert plugin.name == "dbt"


def test_registry_get_airflow():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("airflow")
    assert plugin is not None
    assert plugin.name == "airflow"


def test_registry_get_nonexistent_returns_none():
    reg = _fresh_registry()
    reg.load()
    assert reg.get("nonexistent_xyz_generator") is None


def test_registry_list_all_returns_list():
    reg = _fresh_registry()
    reg.load()
    result = reg.list_all()
    assert isinstance(result, list)
    assert len(result) > 0


def test_registry_list_names_has_dbt():
    reg = _fresh_registry()
    reg.load()
    names = reg.list_names()
    assert "dbt" in names


# ---------------------------------------------------------------------------
# GeneratorPlugin.to_dict
# ---------------------------------------------------------------------------

def test_plugin_to_dict_has_required_keys():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("dbt")
    assert plugin is not None
    d = plugin.to_dict()
    for key in ("name", "class", "module", "source", "description"):
        assert key in d, f"Missing key: {key}"


def test_plugin_source_is_builtin():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("dbt")
    assert plugin is not None
    assert plugin.source == "builtin"


# ---------------------------------------------------------------------------
# Manual register / unregister
# ---------------------------------------------------------------------------

def test_manual_register_plugin():
    reg = _fresh_registry()
    reg.load()

    class FakeGenerator:
        """A fake generator for testing."""
        def generate(self, *args, **kwargs):
            return {}

    reg.register("fake", FakeGenerator, source="plugin")
    plugin = reg.get("fake")
    assert plugin is not None
    assert plugin.name == "fake"
    assert plugin.source == "plugin"


def test_manual_unregister_plugin():
    reg = _fresh_registry()
    reg.load()

    class TempGenerator:
        """Temporary generator."""
        def generate(self, *args, **kwargs):
            return {}

    reg.register("temp", TempGenerator)
    assert reg.get("temp") is not None
    result = reg.unregister("temp")
    assert result is True
    assert reg.get("temp") is None


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------

def test_registry_reload_works():
    reg = _fresh_registry()
    reg.load()
    initial_count = len(reg.list_all())
    reg.reload()
    assert len(reg.list_all()) == initial_count


# ---------------------------------------------------------------------------
# Instance caching
# ---------------------------------------------------------------------------

def test_plugin_instance_is_cached():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("dbt")
    assert plugin is not None
    inst1 = plugin.instance
    inst2 = plugin.instance
    assert inst1 is inst2


# ---------------------------------------------------------------------------
# Generate callable
# ---------------------------------------------------------------------------

def test_plugin_generate_callable():
    reg = _fresh_registry()
    reg.load()
    plugin = reg.get("dbt")
    assert plugin is not None
    # DbtProjectGenerator.generate takes (business_request, constraints)
    from datasphere.models.request import ArchitectureConstraints
    constraints = ArchitectureConstraints(
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="superset",
        deployment="kubernetes",
        security=["RBAC"],
        budget="medium",
        data_lake=None,
        catalog=None,
        quality=None,
    )
    result = plugin.generate("test data pipeline", constraints)
    assert result is not None


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

def test_api_plugins_endpoint_200():
    from fastapi.testclient import TestClient
    from datasphere.api.app import create_app
    client = TestClient(create_app())
    response = client.get("/plugins")
    assert response.status_code == 200


def test_api_plugins_has_builtin_count():
    from fastapi.testclient import TestClient
    from datasphere.api.app import create_app
    client = TestClient(create_app())
    response = client.get("/plugins")
    assert response.status_code == 200
    data = response.json()
    assert "builtin_count" in data
    assert data["builtin_count"] >= 6
    assert "external_count" in data
    assert "count" in data
    assert "plugins" in data
