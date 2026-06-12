from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "iceberg")
class IcebergAdapter(BaseAdapter):
    name = "iceberg"
    category = "storage"

    def connect(self):
        catalog_type = self.config.extra.get("catalog_type", "rest")
        if catalog_type == "rest":
            import urllib.request
            url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8181}/v1/config"
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.read()
        return {"catalog_type": catalog_type}

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        port = self.config.port or 8181
        return f"""  iceberg-rest:
    image: tabulario/iceberg-rest:0.10.0
    ports:
      - "{port}:8181"
    environment:
      CATALOG_WAREHOUSE: s3://iceberg-warehouse/
      CATALOG_IO__IMPL: org.apache.iceberg.aws.s3.S3FileIO
      CATALOG_S3_ENDPOINT: http://minio:9000
      AWS_ACCESS_KEY_ID: ${{MINIO_ROOT_USER}}
      AWS_SECRET_ACCESS_KEY: ${{MINIO_ROOT_PASSWORD}}
      AWS_REGION: us-east-1
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
