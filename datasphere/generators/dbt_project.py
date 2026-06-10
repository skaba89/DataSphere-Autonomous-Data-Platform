"""Génère un scaffold dbt complet à partir des contraintes d'architecture."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datasphere.models.request import ArchitectureConstraints

# Mapping warehouse → dbt adapter package
DBT_ADAPTERS: dict[str, str] = {
    "postgresql":   "dbt-postgres",
    "snowflake":    "dbt-snowflake",
    "bigquery":     "dbt-bigquery",
    "redshift":     "dbt-redshift",
    "databricks":   "dbt-databricks",
    "azure-synapse": "dbt-sqlserver",
    "clickhouse":   "dbt-clickhouse",
    "duckdb":       "dbt-duckdb",
}

# Mapping warehouse → dbt profile type
PROFILE_TYPES: dict[str, str] = {
    "postgresql":    "postgres",
    "snowflake":     "snowflake",
    "bigquery":      "bigquery",
    "redshift":      "redshift",
    "databricks":    "databricks",
    "azure-synapse": "sqlserver",
    "clickhouse":    "clickhouse",
    "duckdb":        "duckdb",
}

# Profil YAML par warehouse
PROFILE_OUTPUTS: dict[str, str] = {
    "postgresql": """\
    dev:
      type: postgres
      host: "{{ env_var('DBT_HOST', 'localhost') }}"
      port: 5432
      user: "{{ env_var('DBT_USER', 'datasphere') }}"
      password: "{{ env_var('DBT_PASSWORD') }}"
      dbname: "{{ env_var('DBT_DATABASE', 'datasphere') }}"
      schema: "{{ env_var('DBT_SCHEMA', 'public') }}"
      threads: 4
""",
    "snowflake": """\
    dev:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
      user: "{{ env_var('SNOWFLAKE_USER') }}"
      password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
      role: "{{ env_var('SNOWFLAKE_ROLE', 'TRANSFORMER') }}"
      database: "{{ env_var('SNOWFLAKE_DATABASE', 'DATASPHERE') }}"
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH') }}"
      schema: "{{ env_var('SNOWFLAKE_SCHEMA', 'PUBLIC') }}"
      threads: 8
      client_session_keep_alive: false
""",
    "bigquery": """\
    dev:
      type: bigquery
      method: oauth
      project: "{{ env_var('GCP_PROJECT') }}"
      dataset: "{{ env_var('BQ_DATASET', 'datasphere') }}"
      threads: 8
      timeout_seconds: 300
      location: "{{ env_var('BQ_LOCATION', 'EU') }}"
      keyfile: "{{ env_var('GOOGLE_APPLICATION_CREDENTIALS', '') }}"
""",
    "redshift": """\
    dev:
      type: redshift
      host: "{{ env_var('REDSHIFT_HOST') }}"
      port: 5439
      user: "{{ env_var('REDSHIFT_USER') }}"
      password: "{{ env_var('REDSHIFT_PASSWORD') }}"
      dbname: "{{ env_var('REDSHIFT_DATABASE', 'dev') }}"
      schema: "{{ env_var('REDSHIFT_SCHEMA', 'public') }}"
      threads: 4
      ra3_node: true
""",
    "databricks": """\
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      catalog: "{{ env_var('DATABRICKS_CATALOG', 'hive_metastore') }}"
      schema: "{{ env_var('DATABRICKS_SCHEMA', 'datasphere') }}"
      threads: 8
""",
    "azure-synapse": """\
    dev:
      type: sqlserver
      driver: "ODBC Driver 18 for SQL Server"
      server: "{{ env_var('SYNAPSE_SERVER') }}"
      port: 1433
      database: "{{ env_var('SYNAPSE_DATABASE', 'datasphere') }}"
      schema: "{{ env_var('SYNAPSE_SCHEMA', 'dbo') }}"
      authentication: sql
      username: "{{ env_var('SYNAPSE_USER') }}"
      password: "{{ env_var('SYNAPSE_PASSWORD') }}"
      threads: 4
""",
    "clickhouse": """\
    dev:
      type: clickhouse
      host: "{{ env_var('CLICKHOUSE_HOST', 'localhost') }}"
      port: 9000
      user: "{{ env_var('CLICKHOUSE_USER', 'default') }}"
      password: "{{ env_var('CLICKHOUSE_PASSWORD', '') }}"
      schema: "{{ env_var('CLICKHOUSE_SCHEMA', 'default') }}"
      threads: 4
""",
    "duckdb": """\
    dev:
      type: duckdb
      path: "{{ env_var('DUCKDB_PATH', 'datasphere.duckdb') }}"
      threads: 4
      schema: "{{ env_var('DUCKDB_SCHEMA', 'main') }}"
""",
}

PROFILE_OUTPUTS["postgresql_default"] = PROFILE_OUTPUTS["postgresql"]


@dataclass
class DbtProjectFiles:
    files: dict[str, str] = field(default_factory=dict)

    def write(self, output_dir: str) -> list[str]:
        base = Path(output_dir) / "dbt"
        written = []
        for rel_path, content in self.files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(str(p))
        return written


class DbtProjectGenerator:
    """Génère un scaffold dbt complet et prêt à l'emploi."""

    def generate(
        self,
        business_request: str,
        constraints: ArchitectureConstraints,
    ) -> DbtProjectFiles:
        wh = constraints.data_warehouse.lower()
        project_name = self._project_name(business_request)
        adapter = DBT_ADAPTERS.get(wh, "dbt-postgres")

        files: dict[str, str] = {}

        files["dbt_project.yml"] = self._dbt_project_yml(project_name, wh)
        files["profiles.yml"] = self._profiles_yml(project_name, wh)
        files["packages.yml"] = self._packages_yml()
        files[".sqlfluff"] = self._sqlfluff(wh)
        files[".gitignore"] = self._gitignore()
        files["README.md"] = self._readme(project_name, business_request, constraints, adapter)

        # Seeds
        files["seeds/.gitkeep"] = ""

        # Macros
        files["macros/generate_schema_name.sql"] = self._macro_schema_name()
        files["macros/audit_helper.sql"] = self._macro_audit_helper()

        # Analyses
        files["analyses/.gitkeep"] = ""

        # Tests
        files["tests/.gitkeep"] = ""

        # Sources
        files["models/staging/sources.yml"] = self._sources_yml(constraints)

        # Staging models
        for src, model, desc in self._staging_models(constraints):
            files[f"models/staging/{src}/{model}.sql"] = self._staging_sql(model, src, wh)
            files[f"models/staging/{src}/schema.yml"] = self._staging_schema_yml(src, model, desc)

        # Intermediate
        files["models/intermediate/.gitkeep"] = ""

        # Marts
        for mart, sql in self._mart_models(business_request, constraints):
            files[f"models/marts/{mart}.sql"] = sql
        files["models/marts/schema.yml"] = self._marts_schema_yml(business_request)

        # Exposures
        files["models/exposures.yml"] = self._exposures_yml(business_request, constraints)

        return DbtProjectFiles(files=files)

    # ------------------------------------------------------------------
    # dbt_project.yml
    # ------------------------------------------------------------------

    def _dbt_project_yml(self, project_name: str, wh: str) -> str:
        wh_config = ""
        if wh in ("snowflake", "bigquery", "redshift", "databricks"):
            wh_config = "\n  +transient: false"
        return f"""name: "{project_name}"
version: "1.0.0"
config-version: 2

profile: "{project_name}"

model-paths: ["models"]
analysis-paths: ["analyses"]
test-paths: ["tests"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
snapshot-paths: ["snapshots"]

target-path: "target"
clean-targets: ["target", "dbt_packages"]

models:
  {project_name}:
    staging:
      +materialized: view
      +schema: staging
    intermediate:
      +materialized: ephemeral
    marts:
      +materialized: table{wh_config}
      +schema: marts

vars:
  start_date: "2024-01-01"
"""

    # ------------------------------------------------------------------
    # profiles.yml
    # ------------------------------------------------------------------

    def _profiles_yml(self, project_name: str, wh: str) -> str:
        output_block = PROFILE_OUTPUTS.get(wh, PROFILE_OUTPUTS["postgresql"])
        return f"""{project_name}:
  target: dev
  outputs:
{output_block}
"""

    # ------------------------------------------------------------------
    # packages.yml
    # ------------------------------------------------------------------

    def _packages_yml(self) -> str:
        return """packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
  - package: dbt-labs/audit_helper
    version: [">=0.9.0", "<1.0.0"]
  - package: dbt-labs/codegen
    version: [">=0.12.0", "<1.0.0"]
  - package: calogica/dbt_expectations
    version: [">=0.10.0", "<1.0.0"]
"""

    # ------------------------------------------------------------------
    # .sqlfluff
    # ------------------------------------------------------------------

    def _sqlfluff(self, wh: str) -> str:
        dialect_map = {
            "postgresql": "postgres",
            "snowflake": "snowflake",
            "bigquery": "bigquery",
            "redshift": "redshift",
            "databricks": "sparksql",
            "azure-synapse": "tsql",
            "clickhouse": "clickhouse",
            "duckdb": "duckdb",
        }
        dialect = dialect_map.get(wh, "ansi")
        return f"""[sqlfluff]
dialect = {dialect}
templater = dbt
runaway_limit = 10
max_line_length = 120
indent_unit = space

[sqlfluff:templater:dbt]
project_dir = .

[sqlfluff:indentation]
indent_unit = space
tab_space_size = 4

[sqlfluff:rules:convention.terminator]
multiline_newline = true
"""

    # ------------------------------------------------------------------
    # .gitignore
    # ------------------------------------------------------------------

    def _gitignore(self) -> str:
        return """target/
dbt_packages/
logs/
*.duckdb
profiles.yml
.env
"""

    # ------------------------------------------------------------------
    # Macros
    # ------------------------------------------------------------------

    def _macro_schema_name(self) -> str:
        return '''{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- set default_schema = target.schema -%}
  {%- if custom_schema_name is none -%}
    {{ default_schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
'''

    def _macro_audit_helper(self) -> str:
        return '''{% macro get_audit_columns() %}
  _loaded_at,
  _source,
  _row_hash
{% endmacro %}

{% macro add_audit_columns(source_table) %}
  *,
  current_timestamp as _loaded_at,
  \'{{ source_table }}\' as _source,
  {{ dbt_utils.generate_surrogate_key(["*"]) }} as _row_hash
{% endmacro %}
'''

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def _sources_yml(self, c: ArchitectureConstraints) -> str:
        return f"""version: 2

sources:
  - name: raw
    description: "Données brutes ingérées par {c.ingestion}"
    database: "{{{{ env_var('DBT_DATABASE', 'datasphere') }}}}"
    schema: raw
    loader: {c.ingestion}
    tables:
      - name: orders
        description: "Table des commandes brutes"
        columns:
          - name: id
            description: "Identifiant unique de commande"
            tests: [not_null, unique]
          - name: created_at
            tests: [not_null]
          - name: customer_id
            tests: [not_null]
          - name: amount
            tests: [not_null]

      - name: customers
        description: "Table des clients bruts"
        columns:
          - name: id
            tests: [not_null, unique]
          - name: email
            tests: [not_null, unique]

      - name: products
        description: "Catalogue produits bruts"
        columns:
          - name: id
            tests: [not_null, unique]
          - name: name
            tests: [not_null]
"""

    # ------------------------------------------------------------------
    # Staging models
    # ------------------------------------------------------------------

    def _staging_models(self, c: ArchitectureConstraints) -> list[tuple[str, str, str]]:
        return [
            ("raw", "stg_orders",    "Commandes normalisées depuis la source brute"),
            ("raw", "stg_customers", "Clients normalisés depuis la source brute"),
            ("raw", "stg_products",  "Produits normalisés depuis la source brute"),
        ]

    def _staging_sql(self, model: str, source: str, wh: str) -> str:
        entity = model.replace("stg_", "")
        cast_date = "cast(created_at as timestamp)" if wh != "bigquery" else "timestamp(created_at)"
        if entity == "orders":
            return f"""with source as (
    select * from {{{{ source('{source}', '{entity}') }}}}
),

renamed as (
    select
        id                                   as order_id,
        customer_id,
        {cast_date}                          as ordered_at,
        amount                               as order_amount_eur,
        coalesce(status, 'unknown')          as order_status,
        lower(trim(channel))                 as channel,
        current_timestamp                    as _loaded_at
    from source
    where id is not null
)

select * from renamed
"""
        elif entity == "customers":
            return f"""with source as (
    select * from {{{{ source('{source}', '{entity}') }}}}
),

renamed as (
    select
        id                                   as customer_id,
        lower(trim(email))                   as email,
        coalesce(first_name, 'Unknown')      as first_name,
        coalesce(last_name, '')              as last_name,
        {cast_date}                          as created_at,
        current_timestamp                    as _loaded_at
    from source
    where id is not null
      and email is not null
)

select * from renamed
"""
        else:
            return f"""with source as (
    select * from {{{{ source('{source}', '{entity}') }}}}
),

renamed as (
    select
        id                                   as product_id,
        name                                 as product_name,
        lower(coalesce(category, 'other'))   as category,
        coalesce(price_eur, 0)               as price_eur,
        current_timestamp                    as _loaded_at
    from source
    where id is not null
)

select * from renamed
"""

    def _staging_schema_yml(self, source: str, model: str, description: str) -> str:
        entity = model.replace("stg_", "")
        id_col = f"{entity[:-1]}_id" if entity.endswith("s") else f"{entity}_id"
        return f"""version: 2

models:
  - name: {model}
    description: "{description}"
    columns:
      - name: {id_col}
        description: "Clé primaire de {entity}"
        tests:
          - not_null
          - unique
      - name: _loaded_at
        description: "Timestamp de chargement"
        tests:
          - not_null
"""

    # ------------------------------------------------------------------
    # Mart models
    # ------------------------------------------------------------------

    def _mart_models(self, business_request: str, c: ArchitectureConstraints) -> list[tuple[str, str]]:
        return [
            ("dim_customers",   self._dim_customers_sql()),
            ("dim_products",    self._dim_products_sql()),
            ("fct_orders",      self._fct_orders_sql()),
            ("agg_daily_sales", self._agg_daily_sales_sql()),
        ]

    def _dim_customers_sql(self) -> str:
        return """with customers as (
    select * from {{ ref('stg_customers') }}
)

select
    customer_id,
    email,
    first_name,
    last_name,
    first_name || ' ' || last_name           as full_name,
    created_at,
    _loaded_at
from customers
"""

    def _dim_products_sql(self) -> str:
        return """with products as (
    select * from {{ ref('stg_products') }}
)

select
    product_id,
    product_name,
    category,
    price_eur,
    _loaded_at
from products
"""

    def _fct_orders_sql(self) -> str:
        return """with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select customer_id from {{ ref('dim_customers') }}
),

products as (
    select product_id from {{ ref('dim_products') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['o.order_id']) }} as order_key,
        o.order_id,
        o.customer_id,
        o.ordered_at,
        date_trunc('day', o.ordered_at)      as order_date,
        o.order_amount_eur,
        o.order_status,
        o.channel,
        o._loaded_at
    from orders o
    left join customers c using (customer_id)
)

select * from final
"""

    def _agg_daily_sales_sql(self) -> str:
        return """with orders as (
    select * from {{ ref('fct_orders') }}
    where order_status not in ('cancelled', 'refunded')
),

daily as (
    select
        order_date,
        channel,
        count(distinct order_id)             as nb_orders,
        count(distinct customer_id)          as nb_customers,
        sum(order_amount_eur)                as total_revenue_eur,
        avg(order_amount_eur)                as avg_order_eur,
        min(order_amount_eur)                as min_order_eur,
        max(order_amount_eur)                as max_order_eur
    from orders
    group by 1, 2
)

select * from daily
"""

    def _marts_schema_yml(self, business_request: str) -> str:
        return f"""version: 2

models:
  - name: dim_customers
    description: "Dimension clients — historique et attributs"
    columns:
      - name: customer_id
        tests: [not_null, unique]
      - name: email
        tests: [not_null, unique]

  - name: dim_products
    description: "Dimension produits — catalogue"
    columns:
      - name: product_id
        tests: [not_null, unique]

  - name: fct_orders
    description: "Table de faits commandes — grain : 1 ligne = 1 commande"
    columns:
      - name: order_key
        tests: [not_null, unique]
      - name: order_id
        tests: [not_null, unique]
      - name: customer_id
        tests: [not_null]
      - name: order_amount_eur
        tests:
          - not_null
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 0
              max_value: 1000000

  - name: agg_daily_sales
    description: "Agrégat ventes journalières par canal"
    columns:
      - name: order_date
        tests: [not_null]
      - name: channel
        tests: [not_null]
"""

    # ------------------------------------------------------------------
    # Exposures
    # ------------------------------------------------------------------

    def _exposures_yml(self, business_request: str, c: ArchitectureConstraints) -> str:
        bi = c.bi_tool
        return f"""version: 2

exposures:
  - name: tableau_de_bord_ventes
    label: "Tableau de bord — {business_request[:60]}"
    type: dashboard
    maturity: high
    url: "http://{bi}.datasphere.internal"
    description: >
      Dashboard principal consommant les marts dbt.
      Mis à jour quotidiennement.
    owner:
      name: DataSphere Team
      email: data@company.com
    depends_on:
      - ref('fct_orders')
      - ref('agg_daily_sales')
      - ref('dim_customers')
      - ref('dim_products')
"""

    # ------------------------------------------------------------------
    # README
    # ------------------------------------------------------------------

    def _readme(
        self, project_name: str, business_request: str,
        c: ArchitectureConstraints, adapter: str
    ) -> str:
        return f"""# dbt Project — {project_name}

> {business_request}

## Stack

| Couche | Outil |
|--------|-------|
| Warehouse | {c.data_warehouse} |
| Ingestion | {c.ingestion} |
| Orchestrateur | {c.orchestrator} |
| BI | {c.bi_tool} |

## Installation

```bash
pip install {adapter}
dbt deps
```

## Structure

```
dbt/
├── models/
│   ├── staging/         # Vues de nettoyage depuis raw
│   │   └── raw/
│   │       ├── stg_orders.sql
│   │       ├── stg_customers.sql
│   │       └── stg_products.sql
│   ├── intermediate/    # Modèles éphémères
│   └── marts/           # Tables finales pour le BI
│       ├── dim_customers.sql
│       ├── dim_products.sql
│       ├── fct_orders.sql
│       └── agg_daily_sales.sql
├── macros/
├── seeds/
├── tests/
├── dbt_project.yml
└── profiles.yml
```

## Commandes utiles

```bash
dbt debug                        # Tester la connexion
dbt deps                         # Installer les packages
dbt seed                         # Charger les seeds
dbt run                          # Exécuter tous les modèles
dbt run --select staging         # Seulement le staging
dbt run --select marts           # Seulement les marts
dbt test                         # Lancer les tests
dbt docs generate && dbt docs serve  # Documenter
dbt build                        # run + test en une commande
```

## Variables d'environnement requises

```bash
DBT_HOST=localhost
DBT_USER=datasphere
DBT_PASSWORD=secret
DBT_DATABASE=datasphere
DBT_SCHEMA=public
```
"""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _project_name(self, business_request: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "_", business_request.lower()).strip("_")
        return slug[:40] or "datasphere_project"
