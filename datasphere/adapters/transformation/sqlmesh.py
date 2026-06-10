from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("transformation", "sqlmesh")
class SQLMeshAdapter(BaseAdapter):
    name = "sqlmesh"
    category = "transformation"

    def connect(self):
        from sqlmesh import Context
        project_path = self.config.extra.get("project_path", ".")
        return Context(paths=[project_path])

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# SQLMesh runs as a CLI tool — no dedicated service required.\n"
            "# Install: pip install sqlmesh\n"
            "# Init:    sqlmesh init <dialect>\n"
            "# Run:     sqlmesh plan && sqlmesh run\n"
        )

    def status(self):
        try:
            import importlib
            importlib.import_module("sqlmesh")
            return {"adapter": self.name, "status": "installed"}
        except ImportError:
            return {"adapter": self.name, "status": "not_installed", "error": "pip install sqlmesh"}
