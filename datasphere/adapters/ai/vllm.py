from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ai", "vllm")
class VLLMAdapter(BaseAdapter):
    name = "vllm"
    category = "ai"

    def connect(self):
        from openai import OpenAI
        return OpenAI(
            api_key="not-needed",
            base_url=f"http://{self.config.host or 'localhost'}:{self.config.port or 8000}/v1",
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("vllm: host is required")
        if not self.config.extra.get("model"):
            errors.append("vllm: model name is required in extra config")
        return errors

    def deploy(self) -> str:
        model = self.config.extra.get("model", "mistralai/Mistral-7B-Instruct-v0.3")
        port = self.config.port or 8000
        return f"""  vllm:
    image: vllm/vllm-openai:latest
    ports:
      - "{port}:{port}"
    environment:
      HUGGING_FACE_HUB_TOKEN: ${{HF_TOKEN}}
    command: --model {model} --port {port} --dtype auto
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - vllm_cache:/root/.cache/huggingface
"""

    def status(self):
        try:
            client = self.connect()
            client.models.list()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
