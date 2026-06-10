from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ai", "ollama")
class OllamaAdapter(BaseAdapter):
    name = "ollama"
    category = "ai"

    def connect(self):
        import requests
        base_url = f"http://{self.config.host or 'localhost'}:{self.config.port or 11434}"
        session = requests.Session()
        session.base_url = base_url
        return session

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  ollama:
    image: ollama/ollama:latest
    ports:
      - "{self.config.port or 11434}:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
"""

    def status(self):
        try:
            import requests
            r = requests.get(f"http://{self.config.host or 'localhost'}:{self.config.port or 11434}/api/tags", timeout=3)
            return {"adapter": self.name, "status": "healthy", "models": [m["name"] for m in r.json().get("models", [])]}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
