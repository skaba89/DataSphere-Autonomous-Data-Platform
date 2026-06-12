from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ai", "lm-studio")
class LMStudioAdapter(BaseAdapter):
    name = "lm-studio"
    category = "ai"

    def connect(self):
        from openai import OpenAI
        return OpenAI(
            api_key="lm-studio",
            base_url=f"http://{self.config.host or 'localhost'}:{self.config.port or 1234}/v1",
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("lm-studio: host is required (LM Studio server address)")
        return errors

    def deploy(self) -> str:
        return (
            "# LM Studio is a desktop application — download from https://lmstudio.ai\n"
            f"# Start local server on port {self.config.port or 1234} via LM Studio UI.\n"
            "# Compatible with OpenAI API format.\n"
        )

    def status(self):
        try:
            client = self.connect()
            client.models.list()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
