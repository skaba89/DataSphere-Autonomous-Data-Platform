from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ai", "anthropic")
class AnthropicAdapter(BaseAdapter):
    name = "anthropic"
    category = "ai"

    def connect(self):
        import anthropic
        return anthropic.Anthropic(api_key=self.config.password or None)

    def validate(self) -> list[str]:
        if not self.config.password:
            return ["anthropic: api_key (password) is required"]
        return []

    def deploy(self) -> str:
        return "# Anthropic is a managed API — set ANTHROPIC_API_KEY in your environment."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
