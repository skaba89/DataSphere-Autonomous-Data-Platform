from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ai", "openai")
class OpenAIAdapter(BaseAdapter):
    name = "openai"
    category = "ai"

    def connect(self):
        from openai import OpenAI
        return OpenAI(api_key=self.config.password or None)

    def validate(self) -> list[str]:
        if not self.config.password:
            return ["openai: api_key (password) is required"]
        return []

    def deploy(self) -> str:
        return "# OpenAI is a managed API — set OPENAI_API_KEY in your environment."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
