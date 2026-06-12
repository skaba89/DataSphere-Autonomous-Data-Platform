from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("vector", "milvus")
class MilvusAdapter(BaseAdapter):
    name = "milvus"
    category = "vector"

    def connect(self):
        from pymilvus import connections
        connections.connect(
            alias="default",
            host=self.config.host or "localhost",
            port=self.config.port or 19530,
        )
        return connections

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("milvus: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 19530
        return f"""  milvus-etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
    command: etcd --advertise-client-urls=http://127.0.0.1:2379 --listen-client-urls http://0.0.0.0:2379

  milvus-minio:
    image: minio/minio:RELEASE.2023-03-13T19-46-17Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    command: minio server /minio_data

  milvus:
    image: milvusdb/milvus:v2.4.4
    command: milvus run standalone
    ports:
      - "{port}:{port}"
      - "9091:9091"
    environment:
      ETCD_ENDPOINTS: milvus-etcd:2379
      MINIO_ADDRESS: milvus-minio:9000
    depends_on:
      - milvus-etcd
      - milvus-minio
"""

    def status(self):
        try:
            from pymilvus import utility
            self.connect()
            utility.list_collections()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
