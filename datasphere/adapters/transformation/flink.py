from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("transformation", "flink")
class FlinkAdapter(BaseAdapter):
    name = "flink"
    category = "transformation"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8081}/overview"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("flink: JobManager host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 8081
        return f"""  flink-jobmanager:
    image: flink:1.19-scala_2.12
    command: jobmanager
    ports:
      - "{port}:8081"
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: flink-jobmanager

  flink-taskmanager:
    image: flink:1.19-scala_2.12
    command: taskmanager
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: flink-jobmanager
        taskmanager.numberOfTaskSlots: 4
    depends_on:
      - flink-jobmanager
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
