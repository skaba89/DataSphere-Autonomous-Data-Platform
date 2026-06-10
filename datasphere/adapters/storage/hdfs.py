from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "hdfs")
class HDFSAdapter(BaseAdapter):
    name = "hdfs"
    category = "storage"

    def connect(self):
        from hdfs import InsecureClient
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 9870}"
        return InsecureClient(url, user=self.config.username or "hadoop")

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("hdfs: NameNode host is required")
        return errors

    def deploy(self) -> str:
        return f"""  hdfs-namenode:
    image: apache/hadoop:3.3.6
    command: hdfs namenode
    ports:
      - "9870:9870"
      - "8020:8020"
    environment:
      HADOOP_HOME: /opt/hadoop

  hdfs-datanode:
    image: apache/hadoop:3.3.6
    command: hdfs datanode
    environment:
      HADOOP_HOME: /opt/hadoop
    depends_on:
      - hdfs-namenode
"""

    def status(self):
        try:
            client = self.connect()
            client.status("/")
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
