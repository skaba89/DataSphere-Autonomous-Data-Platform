# Stack Choice Reference

Complete list of supported tools per layer.

## 1. Cloud Provider
| Value | Description |
|-------|-------------|
| `local-docker` | Docker Compose on local machine |
| `aws` | Amazon Web Services |
| `azure` | Microsoft Azure |
| `gcp` | Google Cloud Platform |
| `ovhcloud` | OVHcloud |
| `scaleway` | Scaleway |
| `on-premise` | Self-hosted bare metal |
| `kubernetes` | Existing Kubernetes cluster |

## 2. Data Warehouse
| Value | Notes |
|-------|-------|
| `postgresql` | Self-hosted, local-docker |
| `snowflake` | Managed SaaS |
| `bigquery` | GCP-native |
| `redshift` | AWS-native |
| `azure-synapse` | Azure-native |
| `databricks` | Multi-cloud |
| `clickhouse` | High-performance OLAP |
| `duckdb` | Embedded, great for local |

## 3. Orchestration
| Value | Notes |
|-------|-------|
| `airflow` | Most popular, mature ecosystem |
| `dagster` | Asset-based, great DX |
| `prefect` | Cloud-native, Python-first |
| `kestra` | YAML-first, low-code |
| `argo` | Kubernetes-native |

## 4. Ingestion
| Value | Notes |
|-------|-------|
| `airbyte` | 300+ connectors, UI-driven |
| `meltano` | Singer-based, CLI-first |
| `nifi` | Visual dataflow |
| `kafka-connect` | Streaming-first |
| `debezium` | CDC specialist |
| `fivetran-like` | Managed connector abstraction |

## 5. Transformation
| Value | Notes |
|-------|-------|
| `dbt` | SQL-first, most popular |
| `sqlmesh` | dbt-compatible + versioning |
| `spark` | Large-scale distributed |
| `flink` | Streaming transformations |
| `polars` | Fast Python dataframes |

## 6. Storage / Data Lake
| Value | Notes |
|-------|-------|
| `minio` | S3-compatible, self-hosted |
| `s3` | AWS native |
| `adls` | Azure Data Lake Storage Gen2 |
| `gcs` | Google Cloud Storage |
| `hdfs` | Hadoop, on-premise |
| `iceberg` | Open table format |
| `delta-lake` | Databricks open table format |
| `hudi` | Upserts & incremental |

## 7. BI / Analytics
| Value | Notes |
|-------|-------|
| `superset` | Apache, open-source, powerful |
| `metabase` | Simple, non-technical users |
| `redash` | SQL-focused |
| `evidence` | Code-first BI |
| `grafana` | Time-series & metrics |
| `powerbi` | Microsoft ecosystem |
| `tableau` | Enterprise standard |

## 8. Data Quality
| Value | Notes |
|-------|-------|
| `great-expectations` | Most popular, Python |
| `soda-core` | YAML-based checks |
| `dbt-tests` | Built into dbt projects |
| `deequ` | Spark-based, AWS |

## 9. Data Catalog / Governance
| Value | Notes |
|-------|-------|
| `openmetadata` | Full-featured, modern |
| `datahub` | LinkedIn, enterprise |
| `amundsen` | Lyft, search-first |
| `marquez` | OpenLineage, lineage-first |

## 10. AI / LLM
| Value | Notes |
|-------|-------|
| `openai` | GPT-4, GPT-4o |
| `azure-openai` | OpenAI via Azure |
| `anthropic` | Claude models |
| `mistral` | EU-based, efficient |
| `ollama` | Local LLM runner |
| `vllm` | High-throughput serving |
| `lm-studio` | Desktop local inference |

## 11. Vector Database
| Value | Notes |
|-------|-------|
| `qdrant` | Rust-based, fast |
| `weaviate` | GraphQL API |
| `milvus` | Large-scale |
| `pgvector` | PostgreSQL extension |
| `chroma` | Developer-friendly |

## 12. Infrastructure
| Value | Notes |
|-------|-------|
| `docker-compose` | Local/simple deployments |
| `kubernetes` | Production clusters |
| `helm` | K8s package manager |
| `terraform` | IaC, multi-cloud |
| `ansible` | Configuration management |
| `github-actions` | CI/CD |
| `gitlab-ci` | CI/CD |

## 13. Monitoring
| Value | Notes |
|-------|-------|
| `prometheus` | Metrics, pull-based |
| `grafana` | Dashboards |
| `loki` | Log aggregation |
| `opentelemetry` | Traces + metrics + logs |
| `elk` | Elasticsearch/Logstash/Kibana |

## 14. Security
| Value | Notes |
|-------|-------|
| `vault` | Secrets management |
| `keycloak` | IdP + SSO |
| `authentik` | Modern IdP |
| `oidc` | Protocol layer |
| `jwt` | Token auth |
| `rbac` | Role-based access |
| `secret-manager` | Cloud-native secrets |
