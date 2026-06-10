from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("vector", "qdrant")
class QdrantAdapter(BaseAdapter):
    name = "qdrant"
    category = "vector"

    def connect(self):
        from qdrant_client import QdrantClient
        return QdrantClient(
            host=self.config.host or "localhost",
            port=self.config.port or 6333,
            api_key=self.config.password or None,
        )

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "{self.config.port or 6333}:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
"""

    def status(self):
        try:
            client = self.connect()
            info = client.get_collections()
            return {"adapter": self.name, "status": "healthy", "collections": len(info.collections)}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
