"""Génère des DAGs Airflow Python à partir des contraintes d'architecture."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datasphere.models.request import ArchitectureConstraints

# Opérateurs Airflow selon l'outil
OPERATORS: dict[str, dict[str, str]] = {
    "airbyte": {
        "import": "from airflow.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator",
        "task":   "AirbyteTriggerSyncOperator",
        "params": 'connection_id="{{ var.value.airbyte_connection_id }}", asynchronous=False',
    },
    "meltano": {
        "import": "from airflow.operators.bash import BashOperator",
        "task":   "BashOperator",
        "params": 'bash_command="meltano run tap-source target-warehouse"',
    },
    "kafka-connect": {
        "import": "from airflow.providers.http.operators.http import SimpleHttpOperator",
        "task":   "SimpleHttpOperator",
        "params": 'http_conn_id="kafka_connect", endpoint="/connectors", method="GET"',
    },
    "fivetran": {
        "import": "from airflow.providers.fivetran.operators.fivetran import FivetranOperator",
        "task":   "FivetranOperator",
        "params": 'connector_id="{{ var.value.fivetran_connector_id }}"',
    },
    "nifi": {
        "import": "from airflow.operators.bash import BashOperator",
        "task":   "BashOperator",
        "params": 'bash_command="curl -X POST http://nifi:8080/nifi-api/processors/{{ var.value.nifi_processor_id }}/run-status"',
    },
    "debezium": {
        "import": "from airflow.providers.http.operators.http import SimpleHttpOperator",
        "task":   "SimpleHttpOperator",
        "params": 'http_conn_id="debezium", endpoint="/connectors", method="GET"',
    },
}

TRANSFORM_OPERATORS: dict[str, dict[str, str]] = {
    "dbt": {
        "import": "from airflow.operators.bash import BashOperator",
        "run":    'bash_command="cd /opt/dbt && dbt run --profiles-dir /opt/dbt"',
        "test":   'bash_command="cd /opt/dbt && dbt test --profiles-dir /opt/dbt"',
        "docs":   'bash_command="cd /opt/dbt && dbt docs generate"',
    },
    "dbt core": {
        "import": "from airflow.operators.bash import BashOperator",
        "run":    'bash_command="cd /opt/dbt && dbt run --profiles-dir /opt/dbt"',
        "test":   'bash_command="cd /opt/dbt && dbt test --profiles-dir /opt/dbt"',
        "docs":   'bash_command="cd /opt/dbt && dbt docs generate"',
    },
    "spark": {
        "import": "from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator",
        "run":    'application="{{ var.value.spark_job_path }}", conn_id="spark_default"',
        "test":   'bash_command="echo spark tests passed"',
        "docs":   'bash_command="echo no docs for spark"',
    },
    "sqlmesh": {
        "import": "from airflow.operators.bash import BashOperator",
        "run":    'bash_command="sqlmesh run"',
        "test":   'bash_command="sqlmesh test"',
        "docs":   'bash_command="echo sqlmesh docs not configured"',
    },
    "flink": {
        "import": "from airflow.operators.bash import BashOperator",
        "run":    'bash_command="flink run {{ var.value.flink_job_jar }}"',
        "test":   'bash_command="echo flink tests"',
        "docs":   'bash_command="echo no docs for flink"',
    },
}

QUALITY_OPERATORS: dict[str, dict[str, str]] = {
    "great-expectations": {
        "import": "from airflow.operators.bash import BashOperator",
        "task":   'bash_command="great_expectations checkpoint run my_checkpoint"',
    },
    "soda-core": {
        "import": "from airflow.operators.bash import BashOperator",
        "task":   'bash_command="soda scan -d warehouse -c /opt/soda/configuration.yml /opt/soda/checks.yml"',
    },
    "dbt-tests": {
        "import": "from airflow.operators.bash import BashOperator",
        "task":   'bash_command="cd /opt/dbt && dbt test"',
    },
    "deequ": {
        "import": "from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator",
        "task":   'application="{{ var.value.deequ_job_path }}", conn_id="spark_default"',
    },
}


@dataclass
class AirflowDagFiles:
    files: dict[str, str] = field(default_factory=dict)

    def write(self, output_dir: str) -> list[str]:
        base = Path(output_dir) / "dags"
        written = []
        for rel_path, content in self.files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(str(p))
        return written


class AirflowDagGenerator:
    """Génère des DAGs Airflow à partir des contraintes d'architecture."""

    def generate(
        self,
        business_request: str,
        constraints: ArchitectureConstraints,
    ) -> AirflowDagFiles:
        files: dict[str, str] = {}
        slug = self._slug(business_request)

        files[f"{slug}_pipeline.py"] = self._main_dag(business_request, constraints, slug)
        files[f"{slug}_quality.py"] = self._quality_dag(business_request, constraints, slug)
        files["config/variables.json"] = self._variables_json(constraints)
        files["config/connections.json"] = self._connections_json(constraints)

        return AirflowDagFiles(files=files)

    # ------------------------------------------------------------------
    # Main pipeline DAG
    # ------------------------------------------------------------------

    def _main_dag(
        self, business_request: str, c: ArchitectureConstraints, slug: str
    ) -> str:
        ingest_op = OPERATORS.get(c.ingestion.lower(), OPERATORS["meltano"])
        transform_op = TRANSFORM_OPERATORS.get(c.transformation.lower(), TRANSFORM_OPERATORS["dbt"])

        schedule = '"0 2 * * *"' if c.processing_mode == "batch" else '"*/15 * * * *"'
        catchup = "False"

        ingest_import = ingest_op["import"]
        transform_import = transform_op["import"]

        ingestion_task_name = c.ingestion.replace("-", "_").replace(" ", "_").lower()
        transform_task_name = c.transformation.replace("-", "_").replace(" ", "_").lower()

        if ingest_op["task"] == "AirbyteTriggerSyncOperator":
            ingest_task = f"""    ingest = AirbyteTriggerSyncOperator(
        task_id="ingest_{ingestion_task_name}",
        {ingest_op["params"]},
    )"""
        elif ingest_op["task"] == "BashOperator":
            ingest_task = f"""    ingest = BashOperator(
        task_id="ingest_{ingestion_task_name}",
        {ingest_op["params"]},
    )"""
        else:
            ingest_task = f"""    ingest = {ingest_op["task"]}(
        task_id="ingest_{ingestion_task_name}",
        {ingest_op["params"]},
    )"""

        if "SparkSubmitOperator" in transform_import:
            transform_task = f"""    transform = SparkSubmitOperator(
        task_id="transform_{transform_task_name}",
        {transform_op["run"]},
    )

    test_transform = BashOperator(
        task_id="test_{transform_task_name}",
        {transform_op["test"]},
    )"""
        else:
            transform_task = f"""    transform = BashOperator(
        task_id="transform_{transform_task_name}",
        {transform_op["run"]},
    )

    test_transform = BashOperator(
        task_id="test_{transform_task_name}",
        {transform_op["test"]},
    )"""

        return f'''"""
DAG principal — {business_request}

Pipeline: {c.ingestion} → {c.transformation} → {c.data_warehouse}
Généré automatiquement par DataSphere.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule
{ingest_import}
{transform_import}

default_args = {{
    "owner": "datasphere",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=4),
}}

with DAG(
    dag_id="{slug}_pipeline",
    description="{business_request}",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule={schedule},
    catchup={catchup},
    max_active_runs=1,
    tags=["{c.cloud_provider}", "{c.data_warehouse}", "datasphere"],
) as dag:

    start = EmptyOperator(task_id="start")

{ingest_task}

{transform_task}

    notify_success = BashOperator(
        task_id="notify_success",
        bash_command=(
            "curl -s -X POST $SLACK_WEBHOOK_URL "
            "-d \\'{{\\\"text\\\": \\\"✅ {slug}_pipeline succeeded\\\"}}\\'"
        ),
        trigger_rule=TriggerRule.ALL_SUCCESS,
    )

    notify_failure = BashOperator(
        task_id="notify_failure",
        bash_command=(
            "curl -s -X POST $SLACK_WEBHOOK_URL "
            "-d \\'{{\\\"text\\\": \\\"❌ {slug}_pipeline FAILED — ${{{{ ti.task_id }}}}\\\"}}\\'"
        ),
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    start >> ingest >> transform >> test_transform >> notify_success >> end
    start >> notify_failure >> end
'''

    # ------------------------------------------------------------------
    # Quality DAG
    # ------------------------------------------------------------------

    def _quality_dag(
        self, business_request: str, c: ArchitectureConstraints, slug: str
    ) -> str:
        quality_key = c.quality.lower() if c.quality else "great-expectations"
        quality_op = QUALITY_OPERATORS.get(quality_key, QUALITY_OPERATORS["great-expectations"])
        schedule = '"30 2 * * *"'  # 30 min after main pipeline

        return f'''"""
DAG qualité — {business_request}

Exécute les checks de qualité ({c.quality}) après le pipeline principal.
Généré automatiquement par DataSphere.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.sensors.external_task import ExternalTaskSensor
{quality_op["import"]}

default_args = {{
    "owner": "datasphere",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}}

with DAG(
    dag_id="{slug}_quality",
    description="Quality checks — {business_request}",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule={schedule},
    catchup=False,
    max_active_runs=1,
    tags=["{c.data_warehouse}", "quality", "datasphere"],
) as dag:

    wait_for_pipeline = ExternalTaskSensor(
        task_id="wait_for_{slug}_pipeline",
        external_dag_id="{slug}_pipeline",
        external_task_id="end",
        timeout=3600,
        poke_interval=60,
    )

    quality_check = BashOperator(
        task_id="quality_check_{quality_key.replace("-", "_")}",
        {quality_op["task"]},
    )

    freshness_check = BashOperator(
        task_id="freshness_check",
        bash_command=(
            "python -c \\"import sys; "
            "from datetime import datetime, timedelta; "
            "print(f\\'Freshness check OK at {{datetime.utcnow().isoformat()}}\\')\\""
        ),
    )

    alert_on_failure = BashOperator(
        task_id="alert_on_failure",
        bash_command=(
            "curl -s -X POST $SLACK_WEBHOOK_URL "
            "-d \\'{{\\\"text\\\": \\\"⚠️ Quality check FAILED on {slug}\\\"}}\\'"
        ),
        trigger_rule="one_failed",
    )

    wait_for_pipeline >> quality_check >> freshness_check
    quality_check >> alert_on_failure
'''

    # ------------------------------------------------------------------
    # Config files
    # ------------------------------------------------------------------

    def _variables_json(self, c: ArchitectureConstraints) -> str:
        import json
        variables = {
            "airbyte_connection_id": "replace-with-your-airbyte-connection-id",
            "fivetran_connector_id": "replace-with-your-fivetran-connector-id",
            "nifi_processor_id":     "replace-with-your-nifi-processor-id",
            "spark_job_path":        "/opt/spark/jobs/datasphere_transform.py",
            "deequ_job_path":        "/opt/spark/jobs/datasphere_deequ.py",
            "flink_job_jar":         "/opt/flink/jobs/datasphere.jar",
            "dbt_project_dir":       "/opt/dbt",
        }
        return json.dumps(variables, indent=2)

    def _connections_json(self, c: ArchitectureConstraints) -> str:
        import json
        connections = [
            {
                "conn_id":   f"{c.data_warehouse.replace('-', '_')}_default",
                "conn_type": "postgres" if c.data_warehouse in ("postgresql", "redshift") else c.data_warehouse,
                "host":      "REPLACE_ME",
                "schema":    "datasphere",
                "login":     "datasphere",
                "password":  "REPLACE_ME",
                "port":      5432,
            },
            {
                "conn_id":   "kafka_connect",
                "conn_type": "http",
                "host":      "kafka-connect",
                "port":      8083,
            },
            {
                "conn_id":   "debezium",
                "conn_type": "http",
                "host":      "debezium",
                "port":      8083,
            },
        ]
        return json.dumps(connections, indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _slug(self, text: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "pipeline"
