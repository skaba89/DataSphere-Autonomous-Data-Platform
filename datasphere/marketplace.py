"""
DataSphere Plugin Marketplace — browse, search, and install community plugins.

The marketplace aggregates:
1. Built-in plugins (always available)
2. Known community plugins (curated list + PyPI search)
3. Installed third-party plugins (via entry_points)
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated community plugin registry
# ---------------------------------------------------------------------------
_CURATED_PLUGINS: list[dict] = [
    {
        "name": "datasphere-duckdb",
        "pypi_package": "datasphere-duckdb",
        "description": "DuckDB warehouse generator for DataSphere",
        "category": "data_warehouse",
        "author": "community",
        "version": "0.1.0",
        "tags": ["duckdb", "warehouse", "analytics", "embedded"],
        "entry_point": "datasphere.generators",
        "stars": 12,
        "verified": False,
    },
    {
        "name": "datasphere-spark",
        "pypi_package": "datasphere-spark",
        "description": "Apache Spark job generator (PySpark, Scala, SparkSQL)",
        "category": "transformation",
        "author": "community",
        "version": "0.2.1",
        "tags": ["spark", "pyspark", "bigdata", "batch"],
        "entry_point": "datasphere.generators",
        "stars": 34,
        "verified": False,
    },
    {
        "name": "datasphere-flink",
        "pypi_package": "datasphere-flink",
        "description": "Apache Flink streaming job generator",
        "category": "streaming",
        "author": "community",
        "version": "0.1.2",
        "tags": ["flink", "streaming", "realtime", "kafka"],
        "entry_point": "datasphere.generators",
        "stars": 8,
        "verified": False,
    },
    {
        "name": "datasphere-pulumi",
        "pypi_package": "datasphere-pulumi",
        "description": "Pulumi IaC generator (alternative to Terraform)",
        "category": "infrastructure",
        "author": "community",
        "version": "0.3.0",
        "tags": ["pulumi", "iac", "infrastructure", "typescript", "python"],
        "entry_point": "datasphere.generators",
        "stars": 21,
        "verified": False,
    },
    {
        "name": "datasphere-dlt",
        "pypi_package": "datasphere-dlt",
        "description": "dlt (data load tool) pipeline generator",
        "category": "ingestion",
        "author": "community",
        "version": "0.1.0",
        "tags": ["dlt", "ingestion", "python", "lightweight"],
        "entry_point": "datasphere.generators",
        "stars": 15,
        "verified": False,
    },
]


@dataclass
class MarketplacePlugin:
    name: str
    pypi_package: str
    description: str
    category: str
    author: str
    version: str
    tags: list[str] = field(default_factory=list)
    stars: int = 0
    verified: bool = False
    installed: bool = False
    installed_version: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pypi_package": self.pypi_package,
            "description": self.description,
            "category": self.category,
            "author": self.author,
            "version": self.version,
            "tags": self.tags,
            "stars": self.stars,
            "verified": self.verified,
            "installed": self.installed,
            "installed_version": self.installed_version,
        }


class PluginMarketplace:
    """Browse, search, and install DataSphere community plugins."""

    def __init__(self) -> None:
        self._curated: list[MarketplacePlugin] = [
            MarketplacePlugin(**{k: v for k, v in p.items() if k != "entry_point"}) for p in _CURATED_PLUGINS
        ]

    def _get_installed_version(self, package: str) -> Optional[str]:
        """Return installed version of a package, or None if not installed."""
        try:
            import importlib.metadata
            return importlib.metadata.version(package)
        except Exception:
            return None

    def _enrich_with_install_status(
        self, plugins: list[MarketplacePlugin]
    ) -> list[MarketplacePlugin]:
        for p in plugins:
            v = self._get_installed_version(p.pypi_package)
            p.installed = v is not None
            p.installed_version = v
        return plugins

    def list_all(self) -> list[MarketplacePlugin]:
        """Return all curated plugins with install status."""
        return self._enrich_with_install_status(list(self._curated))

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        installed_only: bool = False,
    ) -> list[MarketplacePlugin]:
        """Search plugins by name, description, or tags."""
        results = self._enrich_with_install_status(list(self._curated))
        q = query.lower().strip()
        if q:
            results = [
                p for p in results
                if q in p.name.lower()
                or q in p.description.lower()
                or any(q in t for t in p.tags)
            ]
        if category:
            results = [p for p in results if p.category == category]
        if installed_only:
            results = [p for p in results if p.installed]
        return sorted(results, key=lambda p: (-p.stars, p.name))

    def get(self, name: str) -> Optional[MarketplacePlugin]:
        """Get a plugin by name."""
        plugins = self._enrich_with_install_status(list(self._curated))
        return next((p for p in plugins if p.name == name), None)

    def install(self, package: str, upgrade: bool = False) -> dict:
        """
        Install a plugin via pip. Returns {"success": bool, "output": str, "error": str|None}.
        Only allowed when DATASPHERE_ALLOW_PLUGIN_INSTALL=true.
        """
        if os.environ.get("DATASPHERE_ALLOW_PLUGIN_INSTALL", "").lower() != "true":
            return {
                "success": False,
                "output": "",
                "error": "Plugin installation is disabled. Set DATASPHERE_ALLOW_PLUGIN_INSTALL=true to enable.",
            }
        cmd = [sys.executable, "-m", "pip", "install", package]
        if upgrade:
            cmd.append("--upgrade")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "error": "pip install timed out"}
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}

    def uninstall(self, package: str) -> dict:
        """Uninstall a plugin via pip."""
        if os.environ.get("DATASPHERE_ALLOW_PLUGIN_INSTALL", "").lower() != "true":
            return {
                "success": False,
                "output": "",
                "error": "Plugin management is disabled. Set DATASPHERE_ALLOW_PLUGIN_INSTALL=true to enable.",
            }
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", "-y", package],
                capture_output=True, text=True, timeout=60
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}

    def categories(self) -> list[str]:
        """Return all available plugin categories."""
        return sorted({p.category for p in self._curated})


# Module-level singleton
marketplace = PluginMarketplace()
