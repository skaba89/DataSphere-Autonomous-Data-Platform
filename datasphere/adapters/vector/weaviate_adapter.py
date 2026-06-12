from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("vector", "weaviate")
class WeaviateAdapter(BaseAdapter):
    name = "weaviate"
    category = "vector"

    def connect(self):
        import weaviate
        return weaviate.connect_to_custom(
            http_host=self.config.host or "localhost",
            http_port=self.config.port or 8080,
            grpc_host=self.config.host or "localhost",
            grpc_port=50051,
            auth_credentials=weaviate.auth.AuthApiKey(self.config.password) if self.config.password else None,
        )

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.24.0
    ports:
      - "{self.config.port or 8080}:8080"
      - "50051:50051"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: /var/lib/weaviate
    volumes:
      - weaviate_data:/var/lib/weaviate
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
