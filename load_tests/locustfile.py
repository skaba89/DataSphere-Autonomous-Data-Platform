"""
DataSphere API load test — Locust

Usage:
    pip install locust
    locust -f load_tests/locustfile.py --host http://localhost:8000

    # Headless mode (CI):
    locust -f load_tests/locustfile.py --host http://localhost:8000 \
           --users 50 --spawn-rate 5 --run-time 60s --headless
"""
from locust import HttpUser, task, between, events
import json
import random

class DataSphereUser(HttpUser):
    wait_time = between(0.5, 2.0)

    BUSINESS_REQUESTS = [
        "Pipeline analytics ventes e-commerce",
        "Plateforme données RH temps réel",
        "Dashboard KPIs marketing",
        "Data warehouse pour startup fintech",
    ]

    CLOUDS = ["aws", "gcp", "azure"]
    WAREHOUSES = ["snowflake", "bigquery", "postgresql", "redshift"]

    @task(3)
    def health_check(self):
        self.client.get("/healthz")

    @task(2)
    def readyz(self):
        self.client.get("/readyz")

    @task(1)
    def get_jobs(self):
        self.client.get("/jobs")

    @task(1)
    def get_templates(self):
        self.client.get("/templates")

    @task(1)
    def get_catalog(self):
        self.client.get("/stacks/supported")

    @task(1)
    def get_metrics(self):
        self.client.get("/metrics")

    @task(2)
    def generate_dbt(self):
        self.client.post("/dbt/generate", json={
            "business_request": random.choice(self.BUSINESS_REQUESTS),
            "data_warehouse": random.choice(["snowflake", "bigquery", "postgresql"]),
            "ingestion": "airbyte",
        })

    @task(1)
    def generate_terraform(self):
        self.client.post("/terraform/generate", json={
            "business_request": random.choice(self.BUSINESS_REQUESTS),
            "cloud_provider": random.choice(self.CLOUDS),
            "data_warehouse": random.choice(self.WAREHOUSES),
            "deployment": "kubernetes",
            "budget": "medium",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "security": ["RBAC"],
        })

    @task(1)
    def lineage_generate(self):
        self.client.post("/lineage/generate", json={
            "stack": {
                "cloud_provider": random.choice(self.CLOUDS),
                "data_warehouse": random.choice(self.WAREHOUSES),
                "orchestrator": "airflow",
                "ingestion": "airbyte",
                "transformation": "dbt",
                "bi_tool": "metabase",
            }
        })

    @task(1)
    def cost_estimate(self):
        self.client.post("/costs/estimate", json={
            "stack": {
                "cloud_provider": random.choice(self.CLOUDS),
                "data_warehouse": random.choice(self.WAREHOUSES),
                "orchestrator": "airflow",
                "ingestion": "fivetran",
                "transformation": "dbt",
                "bi_tool": "tableau",
            },
            "budget": random.choice(["low", "medium", "enterprise"]),
        })

    @task(1)
    def stack_diff(self):
        self.client.post("/stacks/diff", json={
            "from_stack": {"data_warehouse": "redshift", "orchestrator": "airflow", "ingestion": "fivetran", "bi_tool": "tableau"},
            "to_stack": {"data_warehouse": "snowflake", "orchestrator": "dagster", "ingestion": "airbyte", "bi_tool": "metabase"},
        })

    @task(1)
    def async_generate_and_poll(self):
        resp = self.client.post("/generate", json={
            "mode": "explicit",
            "business_request": random.choice(self.BUSINESS_REQUESTS),
            "cloud_provider": random.choice(self.CLOUDS),
            "data_warehouse": random.choice(self.WAREHOUSES),
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
            "deployment": "kubernetes",
            "budget": "medium",
            "security": ["RBAC"],
        })
        if resp.status_code == 200:
            job_id = resp.json().get("job_id")
            if job_id:
                self.client.get(f"/jobs/{job_id}")


class AdminUser(HttpUser):
    """Simulates an admin doing housekeeping."""
    wait_time = between(5, 10)
    weight = 1  # much fewer admin users

    @task
    def list_jobs(self):
        self.client.get("/jobs")

    @task
    def check_plugins(self):
        self.client.get("/plugins")

    @task
    def check_metrics(self):
        self.client.get("/metrics")
