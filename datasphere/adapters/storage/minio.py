from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "minio")
class MinIOAdapter(BaseAdapter):
    name = "minio"
    category = "storage"

    def connect(self):
        from minio import Minio
        return Minio(
            f"{self.config.host}:{self.config.port or 9000}",
            access_key=self.config.username or "minioadmin",
            secret_key=self.config.password or "minioadmin",
            secure=self.config.extra.get("secure", False),
        )

    def validate(self) -> list[str]:
        if not self.config.host:
            return ["minio: host is required"]
        return []

    def deploy(self) -> str:
        return f"""  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${{MINIO_ROOT_USER:-minioadmin}}
      MINIO_ROOT_PASSWORD: ${{MINIO_ROOT_PASSWORD:-minioadmin}}
    ports:
      - "{self.config.port or 9000}:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
"""
