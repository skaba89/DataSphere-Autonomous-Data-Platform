from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("orchestration", "airflow")
class AirflowAdapter(BaseAdapter):
    name = "airflow"
    category = "orchestration"

    def connect(self):
        import requests
        base = f"http://{self.config.host}:{self.config.port or 8080}/api/v1"
        session = requests.Session()
        session.auth = (self.config.username or "airflow", self.config.password or "airflow")
        return session

    def validate(self) -> list[str]:
        if not self.config.host:
            return ["airflow: host is required"]
        return []

    def deploy(self) -> str:
        return f"""  airflow-webserver:
    image: apache/airflow:2.8.0
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@postgresql/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
      AIRFLOW__WEBSERVER__SECRET_KEY: ${{AIRFLOW_SECRET_KEY}}
    ports:
      - "{self.config.port or 8080}:8080"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./logs:/opt/airflow/logs
    command: webserver
    depends_on:
      - postgresql

  airflow-scheduler:
    image: apache/airflow:2.8.0
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@postgresql/airflow
    volumes:
      - ./dags:/opt/airflow/dags
      - ./logs:/opt/airflow/logs
    command: scheduler
    depends_on:
      - postgresql
"""

    def status(self):
        try:
            session = self.connect()
            r = session.get(f"http://{self.config.host}:{self.config.port or 8080}/api/v1/health")
            return {"adapter": self.name, "status": "healthy" if r.status_code == 200 else "degraded"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
