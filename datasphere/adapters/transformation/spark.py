from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("transformation", "spark")
class SparkAdapter(BaseAdapter):
    name = "spark"
    category = "transformation"

    def connect(self):
        from pyspark.sql import SparkSession
        return (
            SparkSession.builder
            .master(self.config.extra.get("master", "local[*]"))
            .appName("datasphere")
            .getOrCreate()
        )

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  spark-master:
    image: bitnami/spark:3.5
    environment:
      SPARK_MODE: master
    ports:
      - "8090:8080"
      - "7077:7077"

  spark-worker:
    image: bitnami/spark:3.5
    environment:
      SPARK_MODE: worker
      SPARK_MASTER_URL: spark://spark-master:7077
      SPARK_WORKER_MEMORY: {self.config.extra.get("worker_memory", "2G")}
      SPARK_WORKER_CORES: {self.config.extra.get("worker_cores", "2")}
    depends_on:
      - spark-master
"""

    def status(self):
        try:
            spark = self.connect()
            spark.stop()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
