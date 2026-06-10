from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("quality", "great-expectations")
class GreatExpectationsAdapter(BaseAdapter):
    name = "great-expectations"
    category = "quality"

    def connect(self):
        import great_expectations as gx
        return gx.get_context()

    def validate(self) -> list[str]:
        try:
            import great_expectations
            return []
        except ImportError:
            return ["great-expectations: not installed — pip install great-expectations"]

    def deploy(self) -> str:
        return "# Great Expectations runs as a Python library — add 'great-expectations' to your dependencies."

    def status(self):
        errors = self.validate()
        return {"adapter": self.name, "status": "available" if not errors else "unavailable"}
