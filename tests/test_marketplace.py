"""Tests for the DataSphere plugin marketplace."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from datasphere.api.app import create_app

_app = create_app()
_client = TestClient(_app)


# ---------------------------------------------------------------------------
# PluginMarketplace unit tests
# ---------------------------------------------------------------------------

class TestPluginMarketplace:
    def test_list_all_returns_plugins(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        plugins = mp.list_all()
        assert len(plugins) >= 3
        assert all(hasattr(p, "name") for p in plugins)
        assert all(hasattr(p, "pypi_package") for p in plugins)

    def test_search_by_query(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        results = mp.search("spark")
        assert any("spark" in p.name.lower() or "spark" in p.description.lower() for p in results)

    def test_search_empty_query_returns_all(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        all_plugins = mp.list_all()
        search_results = mp.search("")
        assert len(search_results) == len(all_plugins)

    def test_search_by_category(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        results = mp.search(category="infrastructure")
        assert all(p.category == "infrastructure" for p in results)

    def test_search_by_tag(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        results = mp.search("kafka")
        assert any("kafka" in p.tags for p in results)

    def test_get_existing_plugin(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        plugins = mp.list_all()
        first = plugins[0]
        found = mp.get(first.name)
        assert found is not None
        assert found.name == first.name

    def test_get_nonexistent_plugin_returns_none(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        assert mp.get("nonexistent-xyz-12345") is None

    def test_categories_returns_list(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        cats = mp.categories()
        assert isinstance(cats, list)
        assert len(cats) >= 2

    def test_installed_only_filter(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        # No community plugins installed in test env
        results = mp.search(installed_only=True)
        assert isinstance(results, list)
        assert all(p.installed for p in results)

    def test_install_disabled_by_default(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        result = mp.install("some-package")
        assert result["success"] is False
        assert "DATASPHERE_ALLOW_PLUGIN_INSTALL" in result["error"]

    def test_uninstall_disabled_by_default(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        result = mp.uninstall("some-package")
        assert result["success"] is False

    def test_to_dict_has_required_keys(self):
        from datasphere.marketplace import PluginMarketplace
        mp = PluginMarketplace()
        plugin = mp.list_all()[0]
        d = plugin.to_dict()
        for key in ("name", "pypi_package", "description", "category", "author", "version", "tags", "installed"):
            assert key in d, f"Missing key: {key}"

    def test_install_allowed_when_env_set(self, monkeypatch):
        from datasphere.marketplace import PluginMarketplace
        monkeypatch.setenv("DATASPHERE_ALLOW_PLUGIN_INSTALL", "true")
        mp = PluginMarketplace()
        # Try to install a non-existent package — should attempt pip but fail gracefully
        result = mp.install("datasphere-nonexistent-xyz-99999")
        # pip will fail but we should get a structured response
        assert "success" in result
        assert isinstance(result["success"], bool)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestMarketplaceAPI:
    def test_list_marketplace_200(self):
        r = _client.get("/marketplace")
        assert r.status_code == 200
        data = r.json()
        assert "plugins" in data
        assert "count" in data
        assert "categories" in data
        assert data["count"] >= 3

    def test_list_marketplace_search_query(self):
        r = _client.get("/marketplace?q=spark")
        assert r.status_code == 200
        data = r.json()
        assert all(
            "spark" in p["name"].lower() or "spark" in p["description"].lower() or "spark" in p.get("tags", [])
            for p in data["plugins"]
        )

    def test_list_marketplace_category_filter(self):
        r = _client.get("/marketplace?category=infrastructure")
        assert r.status_code == 200
        data = r.json()
        assert all(p["category"] == "infrastructure" for p in data["plugins"])

    def test_get_plugin_by_name(self):
        # First list to get a valid name
        r = _client.get("/marketplace")
        plugins = r.json()["plugins"]
        name = plugins[0]["name"]

        r2 = _client.get(f"/marketplace/{name}")
        assert r2.status_code == 200
        assert r2.json()["name"] == name

    def test_get_nonexistent_plugin_404(self):
        r = _client.get("/marketplace/nonexistent-xyz-12345")
        assert r.status_code == 404

    def test_install_returns_structured_response(self):
        # Should fail (disabled) but return structured JSON
        r = _client.post("/marketplace/datasphere-spark/install")
        assert r.status_code == 200
        data = r.json()
        assert "success" in data
        assert data["success"] is False  # disabled by default

    def test_install_nonexistent_plugin_404(self):
        r = _client.post("/marketplace/nonexistent-xyz-12345/install")
        assert r.status_code == 404

    def test_uninstall_returns_structured_response(self):
        r = _client.delete("/marketplace/datasphere-spark/install")
        assert r.status_code == 200
        data = r.json()
        assert "success" in data

    def test_uninstall_nonexistent_plugin_404(self):
        r = _client.delete("/marketplace/nonexistent-xyz-12345/install")
        assert r.status_code == 404

    def test_v1_marketplace_works(self):
        r = _client.get("/v1/marketplace")
        assert r.status_code == 200
