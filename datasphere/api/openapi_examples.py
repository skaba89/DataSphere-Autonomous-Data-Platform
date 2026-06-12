"""OpenAPI request/response examples for DataSphere API."""

GENERATE_REQUEST_EXAMPLE = {
    "mode": "explicit",
    "business_request": "Pipeline analytics pour e-commerce — ventes, stocks, clients",
    "cloud_provider": "aws",
    "data_warehouse": "snowflake",
    "orchestrator": "airflow",
    "ingestion": "airbyte",
    "transformation": "dbt",
    "bi_tool": "metabase",
    "deployment": "kubernetes",
    "budget": "medium",
    "security": ["RBAC"],
}

GENERATE_RESPONSE_EXAMPLE = {
    "success": True,
    "request_summary": "Pipeline e-commerce sur AWS avec Snowflake",
    "stack_advisor": {
        "validated_stack": {
            "cloud_provider": "aws",
            "data_warehouse": "snowflake",
            "orchestrator": "airflow",
            "ingestion": "airbyte",
            "transformation": "dbt",
            "bi_tool": "metabase",
        },
        "warnings": [],
    },
    "cost_optimization": {
        "total_monthly_usd": 1250,
        "total_yearly_usd": 15000,
    },
}

DBT_REQUEST_EXAMPLE = {
    "business_request": "Analyse des ventes par région et par produit",
    "data_warehouse": "snowflake",
    "ingestion": "airbyte",
}

TERRAFORM_REQUEST_EXAMPLE = {
    "business_request": "Infrastructure data platform e-commerce",
    "cloud_provider": "aws",
    "data_warehouse": "snowflake",
    "deployment": "kubernetes",
    "budget": "medium",
    "orchestrator": "airflow",
    "ingestion": "airbyte",
    "transformation": "dbt",
    "bi_tool": "metabase",
    "security": ["RBAC"],
}

LINEAGE_REQUEST_EXAMPLE = {
    "stack": {
        "cloud_provider": "aws",
        "data_warehouse": "snowflake",
        "orchestrator": "airflow",
        "ingestion": "airbyte",
        "transformation": "dbt",
        "bi_tool": "metabase",
        "quality": "great-expectations",
    }
}

COST_ESTIMATE_REQUEST_EXAMPLE = {
    "stack": {
        "cloud_provider": "aws",
        "data_warehouse": "snowflake",
        "orchestrator": "airflow",
        "ingestion": "fivetran",
        "transformation": "dbt",
        "bi_tool": "tableau",
    },
    "budget": "medium",
}

STACK_DIFF_REQUEST_EXAMPLE = {
    "from_stack": {
        "data_warehouse": "redshift",
        "orchestrator": "airflow",
        "ingestion": "fivetran",
        "bi_tool": "tableau",
    },
    "to_stack": {
        "data_warehouse": "snowflake",
        "orchestrator": "dagster",
        "ingestion": "airbyte",
        "bi_tool": "metabase",
    },
}

WEBHOOK_REQUEST_EXAMPLE = {
    "url": "https://hooks.example.com/datasphere",
    "events": ["job.completed", "job.failed"],
    "secret": "my-hmac-secret",
}

TEMPLATE_GENERATE_EXAMPLE = {
    "template_id": "modern-data-stack-aws",
    "business_request": "Pipeline analytique pour notre startup e-commerce",
    "overrides": {"bi_tool": "metabase"},
}
