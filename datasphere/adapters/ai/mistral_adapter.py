from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ai", "mistral")
class MistralAdapter(BaseAdapter):
    name = "mistral"
    category = "ai"

    def connect(self):
        from mistralai.client import MistralClient
        return MistralClient(api_key=self.config.password or "")

    def validate(self) -> list[str]:
        if not self.config.password:
            return ["mistral: api_key (password) is required"]
        return []

    def deploy(self) -> str:
        return "# Mistral AI is a managed API — set MISTRAL_API_KEY in your environment."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
