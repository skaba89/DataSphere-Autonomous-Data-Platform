from __future__ import annotations
from datasphere.agents.base_agent import BaseAgent
from datasphere.models.request import BusinessRequest, ArchitectureConstraints
from datasphere.models.output import AgentOutput, CloudArchitectOutput


# Cloud-native service mapping: cloud → managed equivalents for each layer
CLOUD_SERVICES: dict[str, dict[str, str]] = {
    "aws": {
        "warehouse":      "Amazon Redshift / Redshift Serverless",
        "storage":        "Amazon S3",
        "orchestration":  "Amazon MWAA (Managed Airflow) / Step Functions",
        "streaming":      "Amazon Kinesis / MSK (Kafka)",
        "compute":        "Amazon EKS / ECS",
        "secrets":        "AWS Secrets Manager / Parameter Store",
        "iam":            "AWS IAM + Lake Formation (column-level RLS)",
        "monitoring":     "Amazon CloudWatch / X-Ray",
        "catalog":        "AWS Glue Data Catalog",
        "network":        "VPC + Private Subnets + NAT Gateway",
        "registry":       "Amazon ECR",
        "ci_cd":          "AWS CodePipeline / GitHub Actions",
    },
    "azure": {
        "warehouse":      "Azure Synapse Analytics / Azure SQL",
        "storage":        "Azure Data Lake Storage Gen2",
        "orchestration":  "Azure Data Factory / Managed Airflow",
        "streaming":      "Azure Event Hubs (Kafka-compatible)",
        "compute":        "Azure AKS",
        "secrets":        "Azure Key Vault",
        "iam":            "Azure Active Directory + RBAC + Row-level security",
        "monitoring":     "Azure Monitor / Application Insights",
        "catalog":        "Microsoft Purview",
        "network":        "Azure Virtual Network + Private Endpoints",
        "registry":       "Azure Container Registry",
        "ci_cd":          "Azure DevOps / GitHub Actions",
    },
    "gcp": {
        "warehouse":      "BigQuery",
        "storage":        "Google Cloud Storage",
        "orchestration":  "Cloud Composer (Managed Airflow) / Workflows",
        "streaming":      "Google Pub/Sub / Dataflow",
        "compute":        "Google Kubernetes Engine (GKE)",
        "secrets":        "Google Secret Manager",
        "iam":            "Google IAM + BigQuery Column/Row policies",
        "monitoring":     "Cloud Monitoring / Cloud Trace",
        "catalog":        "Dataplex / Data Catalog",
        "network":        "VPC + Private Google Access",
        "registry":       "Google Artifact Registry",
        "ci_cd":          "Cloud Build / GitHub Actions",
    },
    "local-docker": {
        "warehouse":      "Self-hosted (PostgreSQL / ClickHouse / DuckDB)",
        "storage":        "MinIO (S3-compatible)",
        "orchestration":  "Self-hosted Airflow / Dagster / Prefect",
        "streaming":      "Self-hosted Kafka / Redpanda",
        "compute":        "Docker Compose",
        "secrets":        "HashiCorp Vault (dev mode)",
        "iam":            "App-level RBAC + JWT",
        "monitoring":     "Prometheus + Grafana",
        "catalog":        "Self-hosted OpenMetadata / DataHub",
        "network":        "Docker bridge network",
        "registry":       "Local Docker registry / Docker Hub",
        "ci_cd":          "GitHub Actions / GitLab CI",
    },
    "kubernetes": {
        "warehouse":      "Operator-deployed (Postgres, ClickHouse, etc.)",
        "storage":        "MinIO Operator / Cloud PVC",
        "orchestration":  "Argo Workflows / Airflow K8s Executor",
        "streaming":      "Strimzi Kafka Operator",
        "compute":        "Kubernetes (existing cluster)",
        "secrets":        "HashiCorp Vault + Vault Agent Injector",
        "iam":            "K8s RBAC + Namespace isolation",
        "monitoring":     "Prometheus Operator + Grafana",
        "catalog":        "Helm-deployed OpenMetadata",
        "network":        "Ingress Controller + NetworkPolicies",
        "registry":       "External registry (ECR/ACR/GCR/DockerHub)",
        "ci_cd":          "ArgoCD / Flux / GitHub Actions",
    },
}

DEFAULT_REGIONS: dict[str, str] = {
    "aws": "eu-west-1",
    "azure": "westeurope",
    "gcp": "europe-west1",
    "local-docker": "local",
    "kubernetes": "local",
    "ovhcloud": "gra",
    "scaleway": "fr-par",
    "on-premise": "on-premise",
}

TOPOLOGY_BY_DEPLOYMENT: dict[str, dict] = {
    "kubernetes": {
        "zones": ["zone-a", "zone-b", "zone-c"],
        "namespaces": ["datasphere-data", "datasphere-orchestration", "datasphere-bi", "datasphere-monitoring"],
        "ingress": "NGINX Ingress Controller",
        "storage_class": "cloud-dynamic / local-path",
    },
    "docker-compose": {
        "network": "datasphere-bridge",
        "volumes": "named Docker volumes",
        "exposure": "localhost ports",
    },
    "managed": {
        "network": "Cloud VPC + Private Subnets",
        "connectivity": "Private endpoints / PrivateLink",
        "exposure": "API Gateway / Load Balancer",
    },
}


class CloudArchitectAgent(BaseAgent):
    name = "cloud-architect"
    description = "Valide et enrichit les choix cloud, propose la topologie réseau et les services managés."

    def _run(self, request: BusinessRequest, context: dict) -> CloudArchitectOutput:
        c = self._constraints(request)
        provider = c.cloud_provider
        region = c.region or DEFAULT_REGIONS.get(provider, "")
        services = CLOUD_SERVICES.get(provider, CLOUD_SERVICES["local-docker"])

        # Deployment topology
        depl = c.deployment.lower().replace(" ", "-")
        if "kubernetes" in depl or "helm" in depl or "argo" in c.orchestrator:
            topo_key = "kubernetes"
        elif "managed" in depl or "terraform" in depl and provider in ("aws", "azure", "gcp"):
            topo_key = "managed"
        else:
            topo_key = "docker-compose"
        topology = TOPOLOGY_BY_DEPLOYMENT.get(topo_key, {})

        recommendations = self._build_recommendations(c, provider, services)
        active_services = self._active_services(c, services)

        output = CloudArchitectOutput(
            provider=provider,
            region=region,
            services=active_services,
            network_topology=topology,
            recommendations=recommendations,
        )
        output.artifacts["cloud_summary.md"] = self._render_summary(
            request, provider, region, services, topology, recommendations
        )
        return output

    def _active_services(self, c: ArchitectureConstraints, services: dict[str, str]) -> list[str]:
        active = [
            f"Warehouse: {services['warehouse']}",
            f"Compute: {services['compute']}",
            f"Secrets: {services['secrets']}",
            f"Monitoring: {services['monitoring']}",
            f"Network: {services['network']}",
        ]
        if c.data_lake:
            active.append(f"Storage/Lake: {services['storage']}")
        if c.catalog:
            active.append(f"Catalog: {services['catalog']}")
        if c.processing_mode in ("realtime", "both"):
            active.append(f"Streaming: {services['streaming']}")
        return active

    def _build_recommendations(
        self, c: ArchitectureConstraints, provider: str, services: dict[str, str]
    ) -> list[str]:
        recs = []

        if provider == "aws" and c.data_warehouse in ("snowflake", "bigquery"):
            recs.append(
                f"Vous êtes sur AWS mais avez choisi {c.data_warehouse}. "
                "Redshift Serverless sera plus économique et natif. Considérez la migration."
            )
        if provider == "azure" and c.data_warehouse == "bigquery":
            recs.append("BigQuery n'est pas natif Azure. Synapse Analytics est recommandé.")
        if provider == "gcp" and c.data_warehouse != "bigquery":
            recs.append(
                f"Sur GCP, BigQuery est serverless et zéro maintenance. "
                f"Votre choix ({c.data_warehouse}) nécessite de la gestion d'infra supplémentaire."
            )
        if provider in ("aws", "azure", "gcp") and c.deployment in ("docker-compose", "local-docker"):
            recs.append(
                f"Vous déployez sur {provider} mais utilisez Docker Compose. "
                "Kubernetes (EKS/AKS/GKE) est recommandé pour la production."
            )
        if c.processing_mode == "realtime" and c.orchestrator == "airflow":
            recs.append(
                "Airflow n'est pas adapté au streaming temps réel. "
                "Prefect ou Argo + Kafka Connect sont plus adaptés."
            )
        if c.budget == "low" and provider in ("aws", "azure", "gcp"):
            recs.append(
                "Budget faible sur cloud public : activez les instances spot/preemptible "
                "pour réduire les coûts de 60-80% sur les workloads batch."
            )
        if not recs:
            recs.append("Architecture cloud cohérente — aucun conflit détecté.")
        return recs

    def _render_summary(
        self, request: BusinessRequest, provider: str, region: str,
        services: dict[str, str], topology: dict, recommendations: list[str]
    ) -> str:
        c = request.architecture_constraints
        lines = [
            f"# Cloud Architecture — {request.business_request}",
            "",
            f"**Provider:** {provider}  |  **Region:** {region}",
            "",
            "## Services activés",
            "",
        ]
        for k, v in services.items():
            lines.append(f"- **{k.capitalize()}**: {v}")
        lines += [
            "",
            "## Topologie réseau",
            "",
        ]
        for k, v in topology.items():
            lines.append(f"- **{k}**: {v}")
        lines += [
            "",
            "## Recommandations de l'architecte",
            "",
        ]
        for r in recommendations:
            lines.append(f"- {r}")
        return "\n".join(lines)
