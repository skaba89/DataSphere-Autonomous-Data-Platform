from __future__ import annotations
from datasphere.agents.base_agent import BaseAgent
from datasphere.models.request import BusinessRequest
from datasphere.models.output import AgentOutput, SecurityComplianceOutput

# RBAC role templates per business domain
RBAC_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "sales": {
        "data_engineer":    ["READ", "WRITE", "EXECUTE_PIPELINE"],
        "analyst":          ["READ"],
        "manager":          ["READ", "EXPORT"],
        "admin":            ["READ", "WRITE", "DELETE", "MANAGE_USERS"],
        "api_service":      ["READ"],
    },
    "healthcare": {
        "data_engineer":    ["READ", "WRITE", "EXECUTE_PIPELINE"],
        "clinician":        ["READ_OWN_PATIENTS"],
        "researcher":       ["READ_ANONYMIZED"],
        "admin":            ["READ", "WRITE", "DELETE", "MANAGE_USERS", "AUDIT"],
        "auditor":          ["READ_AUDIT_LOGS"],
        "api_service":      ["READ"],
    },
    "finance": {
        "data_engineer":    ["READ", "WRITE", "EXECUTE_PIPELINE"],
        "analyst":          ["READ"],
        "compliance":       ["READ", "READ_AUDIT_LOGS"],
        "executive":        ["READ", "EXPORT"],
        "admin":            ["READ", "WRITE", "DELETE", "MANAGE_USERS", "AUDIT"],
        "api_service":      ["READ"],
    },
    "default": {
        "data_engineer":    ["READ", "WRITE", "EXECUTE_PIPELINE"],
        "analyst":          ["READ"],
        "admin":            ["READ", "WRITE", "DELETE", "MANAGE_USERS"],
        "viewer":           ["READ"],
        "api_service":      ["READ"],
    },
}

# RLS (Row-Level Security) policy templates per warehouse
RLS_TEMPLATES: dict[str, list[str]] = {
    "snowflake": [
        "-- Snowflake Row Access Policy",
        "CREATE OR REPLACE ROW ACCESS POLICY agency_access_policy",
        "AS (agency_id VARCHAR) RETURNS BOOLEAN ->",
        "  CURRENT_ROLE() = 'ADMIN'",
        "  OR EXISTS (",
        "    SELECT 1 FROM user_agency_mapping",
        "    WHERE user_email = CURRENT_USER()",
        "    AND agency_id = agency_id",
        "  );",
        "",
        "ALTER TABLE sales_facts ADD ROW ACCESS POLICY agency_access_policy ON (agency_id);",
    ],
    "bigquery": [
        "-- BigQuery Row-level security via authorized views",
        "CREATE OR REPLACE VIEW `project.dataset.sales_by_agency_view` AS",
        "SELECT * FROM `project.dataset.sales_facts`",
        "WHERE agency_id IN (",
        "  SELECT agency_id FROM `project.dataset.user_agency_mapping`",
        "  WHERE user_email = SESSION_USER()",
        ");",
        "",
        "-- Grant access to view, not base table",
        "GRANT `roles/bigquery.dataViewer` ON VIEW `project.dataset.sales_by_agency_view`",
        "TO 'group:analysts@company.com';",
    ],
    "postgresql": [
        "-- PostgreSQL Row Level Security",
        "ALTER TABLE sales_facts ENABLE ROW LEVEL SECURITY;",
        "",
        "CREATE POLICY agency_isolation ON sales_facts",
        "  USING (agency_id = current_setting('app.current_agency_id')::UUID);",
        "",
        "CREATE POLICY admin_all ON sales_facts",
        "  TO admin_role",
        "  USING (true);",
        "",
        "-- Set agency context at session level",
        "SET app.current_agency_id = 'agency-uuid-here';",
    ],
    "redshift": [
        "-- Redshift Dynamic Data Masking + RLS",
        "CREATE RLS POLICY agency_policy",
        "WITH (agency_id VARCHAR)",
        "USING (agency_id = current_user_agency());",
        "",
        "ATTACH RLS POLICY agency_policy ON sales_facts TO ROLE analyst_role;",
    ],
    "azure-synapse": [
        "-- Azure Synapse Row-Level Security",
        "CREATE SCHEMA Security;",
        "GO",
        "",
        "CREATE FUNCTION Security.fn_AgencyAccessPredicate(@AgencyId AS NVARCHAR(50))",
        "RETURNS TABLE",
        "WITH SCHEMABINDING",
        "AS RETURN SELECT 1 AS fn_Result",
        "WHERE DATABASE_PRINCIPAL_ID() = DATABASE_PRINCIPAL_ID('dbo')",
        "OR EXISTS (SELECT 1 FROM dbo.UserAgencyMapping",
        "           WHERE UserEmail = USER_NAME() AND AgencyId = @AgencyId);",
        "GO",
        "",
        "CREATE SECURITY POLICY AgencyFilter",
        "ADD FILTER PREDICATE Security.fn_AgencyAccessPredicate(agency_id) ON dbo.SalesFacts",
        "WITH (STATE = ON);",
    ],
    "default": [
        "-- RLS à implémenter via votre warehouse",
        "-- Consultez la documentation de votre warehouse cible.",
    ],
}

# Secret management per tool
SECRET_STRATEGIES: dict[str, str] = {
    "vault": (
        "HashiCorp Vault (AppRole auth) — tous les secrets injectés via "
        "Vault Agent Sidecar ou API. Rotation automatique activée. "
        "Audit log vers SIEM."
    ),
    "aws": (
        "AWS Secrets Manager — rotation automatique native. "
        "Accès via IAM Roles (pas de credentials statiques). "
        "Intégration Kubernetes via External Secrets Operator."
    ),
    "azure": (
        "Azure Key Vault — accès via Managed Identity (pas de secrets dans le code). "
        "Intégration AKS via CSI Driver."
    ),
    "gcp": (
        "Google Secret Manager — accès via Workload Identity. "
        "Pas de service account keys sur disque."
    ),
    "simple": (
        "Variables d'environnement chiffrées (.env.enc) + Docker secrets. "
        "Rotation manuelle à planifier trimestriellement."
    ),
}

ENCRYPTION_CONFIGS: dict[str, dict[str, str]] = {
    "aws": {
        "at_rest":    "AES-256 via AWS KMS (Customer Managed Keys)",
        "in_transit": "TLS 1.3 — certificats ACM",
        "database":   "Redshift/RDS encryption at rest activé par défaut",
    },
    "azure": {
        "at_rest":    "Azure Storage Service Encryption + Customer-managed keys (CMK)",
        "in_transit": "TLS 1.3 — certificats Azure",
        "database":   "Synapse Transparent Data Encryption (TDE)",
    },
    "gcp": {
        "at_rest":    "AES-256 par défaut — Cloud KMS pour CMK",
        "in_transit": "TLS 1.3 automatique — Google managed",
        "database":   "BigQuery encryption at rest par défaut",
    },
    "local-docker": {
        "at_rest":    "Volume chiffrement OS (dm-crypt/LUKS)",
        "in_transit": "TLS via Let's Encrypt ou certificats auto-signés",
        "database":   "pg_tde (PostgreSQL) ou chiffrement applicatif",
    },
    "kubernetes": {
        "at_rest":    "etcd encryption + Sealed Secrets ou External Secrets",
        "in_transit": "mTLS via cert-manager + service mesh (Istio/Linkerd)",
        "database":   "Encryption au niveau de la StorageClass",
    },
}

COMPLIANCE_NOTES: dict[str, list[str]] = {
    "healthcare": [
        "RGPD : données de santé = données sensibles (art. 9 RGPD) — DPO obligatoire.",
        "HDS (Hébergeur Données de Santé) : certification requise en France.",
        "Pseudonymisation ou anonymisation des données patients en dehors des environnements cliniques.",
        "Journal d'audit HIPAA/HDS sur tous les accès aux données patients.",
        "Durée de conservation réglementée — purge automatique à configurer.",
    ],
    "finance": [
        "RGPD : base légale requise pour chaque traitement.",
        "SOX/DSP2 : piste d'audit complète sur les transactions financières.",
        "PCI-DSS si données de paiement : chiffrement des PAN, tokenisation.",
        "Ségrégation des environnements (prod ≠ dev) — pas de données réelles en dev.",
    ],
    "default": [
        "RGPD : minimisation des données, base légale documentée.",
        "Pas de données PII en clair dans les logs.",
        "Chiffrement en transit et au repos obligatoire.",
        "Revue trimestrielle des accès (IAM review).",
    ],
}


def _detect_domain(business_request: str) -> str:
    req = business_request.lower()
    if any(w in req for w in ("hospit", "santé", "médic", "patient", "cliniq", "soin")):
        return "healthcare"
    if any(w in req for w in ("paiement", "financ", "bancaire", "crédit", "transaction")):
        return "finance"
    if any(w in req for w in ("vente", "agence", "commercial", "chiffre")):
        return "sales"
    return "default"


class SecurityComplianceAgent(BaseAgent):
    name = "security-compliance"
    description = "Configure RBAC, RLS, secrets, chiffrement et compliance selon le contexte métier."

    def _run(self, request: BusinessRequest, context: dict) -> SecurityComplianceOutput:
        c = self._constraints(request)
        domain = _detect_domain(request.business_request)
        security_controls = [s.lower() for s in c.security]

        # RBAC
        rbac = RBAC_TEMPLATES.get(domain, RBAC_TEMPLATES["default"])

        # RLS
        wh_key = c.data_warehouse.lower()
        rls_lines = RLS_TEMPLATES.get(wh_key, RLS_TEMPLATES["default"])
        rls_policies = rls_lines if "rls" in security_controls else []

        # Secret strategy
        if "vault" in security_controls or "vault" in c.security:
            secret_strategy = SECRET_STRATEGIES["vault"]
        else:
            secret_strategy = SECRET_STRATEGIES.get(c.cloud_provider, SECRET_STRATEGIES["simple"])

        # Encryption
        encryption = ENCRYPTION_CONFIGS.get(c.cloud_provider, ENCRYPTION_CONFIGS["local-docker"])

        # Compliance
        compliance = COMPLIANCE_NOTES.get(domain, COMPLIANCE_NOTES["default"])

        output = SecurityComplianceOutput(
            rbac_config=rbac,
            rls_policies=rls_policies,
            secret_strategy=secret_strategy,
            encryption_config=encryption,
            compliance_notes=compliance,
        )
        output.artifacts["rbac_config.yaml"] = self._render_rbac_yaml(rbac, c.data_warehouse)
        output.artifacts["rls_policies.sql"] = "\n".join(rls_lines)
        output.artifacts["security_report.md"] = self._render_report(
            request, domain, rbac, rls_lines, secret_strategy, encryption, compliance, security_controls
        )
        return output

    def _render_rbac_yaml(self, rbac: dict, warehouse: str) -> str:
        lines = [
            f"# RBAC Configuration — DataSphere",
            f"# Warehouse: {warehouse}",
            "",
            "roles:",
        ]
        for role, permissions in rbac.items():
            lines.append(f"  {role}:")
            lines.append(f"    permissions:")
            for perm in permissions:
                lines.append(f"      - {perm}")
        lines += [
            "",
            "# Assign roles to users/groups",
            "assignments:",
            "  - user: data_team@company.com",
            "    role: data_engineer",
            "  - group: analysts@company.com",
            "    role: analyst",
            "  - service: pipeline-sa",
            "    role: api_service",
        ]
        return "\n".join(lines)

    def _render_report(
        self, request: BusinessRequest, domain: str, rbac: dict,
        rls: list, secret: str, encryption: dict, compliance: list, controls: list
    ) -> str:
        c = request.architecture_constraints
        lines = [
            f"# Security & Compliance Report — {request.business_request}",
            "",
            f"**Domaine détecté:** {domain}  |  **Cloud:** {c.cloud_provider}  "
            f"|  **Warehouse:** {c.data_warehouse}",
            f"**Contrôles demandés:** {', '.join(c.security) or 'défaut'}",
            "",
            "## RBAC — Rôles et permissions",
            "",
            "| Rôle | Permissions |",
            "|------|-------------|",
        ]
        for role, perms in rbac.items():
            lines.append(f"| `{role}` | {', '.join(perms)} |")

        if rls:
            lines += ["", "## RLS — Row Level Security", "", "```sql"]
            lines.extend(rls)
            lines.append("```")

        lines += [
            "",
            "## Gestion des secrets",
            "",
            f"> {secret}",
            "",
            "## Chiffrement",
            "",
        ]
        for k, v in encryption.items():
            lines.append(f"- **{k.replace('_', ' ').title()}**: {v}")

        lines += [
            "",
            "## Conformité réglementaire",
            "",
        ]
        for note in compliance:
            lines.append(f"- {note}")

        if "jwt" in controls:
            lines += [
                "",
                "## JWT Configuration",
                "",
                "```yaml",
                "jwt:",
                "  algorithm: RS256",
                "  expiry: 3600s",
                "  refresh_expiry: 86400s",
                "  issuer: datasphere-auth",
                "  audience: datasphere-api",
                "```",
            ]

        return "\n".join(lines)
