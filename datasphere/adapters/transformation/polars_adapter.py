from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("transformation", "polars")
class PolarsAdapter(BaseAdapter):
    name = "polars"
    category = "transformation"

    def connect(self):
        import polars as pl
        return pl

    def validate(self) -> list[str]:
        try:
            import polars
            return []
        except ImportError:
            return ["polars: not installed — pip install polars"]

    def deploy(self) -> str:
        return "# Polars is a Python library — add 'polars' to your project dependencies."

    def status(self):
        errors = self.validate()
        return {"adapter": self.name, "status": "available" if not errors else "unavailable"}
