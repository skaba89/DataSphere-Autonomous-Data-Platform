from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("vector", "chroma")
class ChromaAdapter(BaseAdapter):
    name = "chroma"
    category = "vector"

    def connect(self):
        import chromadb
        return chromadb.HttpClient(
            host=self.config.host or "localhost",
            port=self.config.port or 8000,
        )

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  chroma:
    image: ghcr.io/chroma-core/chroma:latest
    ports:
      - "{self.config.port or 8000}:8000"
    volumes:
      - chroma_data:/chroma/chroma
"""

    def status(self):
        try:
            client = self.connect()
            client.heartbeat()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
