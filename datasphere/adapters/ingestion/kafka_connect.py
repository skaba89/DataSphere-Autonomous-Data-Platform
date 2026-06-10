from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ingestion", "kafka-connect")
class KafkaConnectAdapter(BaseAdapter):
    name = "kafka-connect"
    category = "ingestion"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8083}/connectors"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("kafka-connect: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 8083
        return f"""  kafka:
    image: confluentinc/cp-kafka:7.6.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    depends_on:
      - zookeeper

  kafka-connect:
    image: confluentinc/cp-kafka-connect:7.6.0
    ports:
      - "{port}:{port}"
    environment:
      CONNECT_BOOTSTRAP_SERVERS: kafka:9092
      CONNECT_REST_PORT: {port}
      CONNECT_GROUP_ID: datasphere-connect
      CONNECT_CONFIG_STORAGE_TOPIC: _connect-configs
      CONNECT_OFFSET_STORAGE_TOPIC: _connect-offsets
      CONNECT_STATUS_STORAGE_TOPIC: _connect-status
      CONNECT_KEY_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      CONNECT_VALUE_CONVERTER: org.apache.kafka.connect.json.JsonConverter
    depends_on:
      - kafka
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
