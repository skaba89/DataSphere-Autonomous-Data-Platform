from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("monitoring", "elk")
class ELKAdapter(BaseAdapter):
    name = "elk"
    category = "monitoring"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 9200}/_cluster/health"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("elk: Elasticsearch host is required")
        return errors

    def deploy(self) -> str:
        es_port = self.config.port or 9200
        return f"""  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.14.0
    ports:
      - "{es_port}:9200"
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms512m -Xmx512m"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data

  logstash:
    image: docker.elastic.co/logstash/logstash:8.14.0
    ports:
      - "5044:5044"
    volumes:
      - ./logstash/pipeline:/usr/share/logstash/pipeline
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.14.0
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:{es_port}
    depends_on:
      - elasticsearch
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
