from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentOutput:
    agent: str
    success: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloudArchitectOutput(AgentOutput):
    agent: str = "cloud-architect"
    provider: str = ""
    region: str = ""
    services: list[str] = field(default_factory=list)
    network_topology: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class InfrastructureOutput(AgentOutput):
    agent: str = "infrastructure"
    deployment_type: str = ""
    # artifacts contains: docker-compose.yml, terraform files, helm values, etc.


@dataclass
class StackAdvisorOutput(AgentOutput):
    agent: str = "stack-advisor"
    validated_stack: dict[str, str] = field(default_factory=dict)
    alternatives: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    compatibility_matrix: dict[str, bool] = field(default_factory=dict)


@dataclass
class CostEstimate:
    service: str
    monthly_usd: float
    tier: str
    notes: str = ""


@dataclass
class CostOptimizationOutput(AgentOutput):
    agent: str = "cost-optimization"
    estimates: list[CostEstimate] = field(default_factory=list)
    total_monthly_usd: float = 0.0
    total_yearly_usd: float = 0.0
    optimizations: list[str] = field(default_factory=list)
    alternative_stack: Optional[dict[str, str]] = None
    savings_usd: float = 0.0


@dataclass
class SecurityComplianceOutput(AgentOutput):
    agent: str = "security-compliance"
    rbac_config: dict[str, Any] = field(default_factory=dict)
    rls_policies: list[str] = field(default_factory=list)
    secret_strategy: str = ""
    encryption_config: dict[str, str] = field(default_factory=dict)
    compliance_notes: list[str] = field(default_factory=list)


@dataclass
class DeploymentOutput(AgentOutput):
    agent: str = "deployment"
    cicd_platform: str = ""
    pipeline_stages: list[str] = field(default_factory=list)
    rollback_strategy: str = ""
    monitoring_config: dict[str, Any] = field(default_factory=dict)
    health_checks: list[str] = field(default_factory=list)


@dataclass
class OrchestratorOutput:
    request_summary: str = ""
    cloud_architect: Optional[CloudArchitectOutput] = None
    stack_advisor: Optional[StackAdvisorOutput] = None
    infrastructure: Optional[InfrastructureOutput] = None
    cost_optimization: Optional[CostOptimizationOutput] = None
    security_compliance: Optional[SecurityComplianceOutput] = None
    deployment: Optional[DeploymentOutput] = None
    artifacts_path: str = ""
    success: bool = True
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Request   : {self.request_summary}",
            f"Success   : {self.success}",
        ]
        if self.cost_optimization:
            lines.append(f"Cost/month: ${self.cost_optimization.total_monthly_usd:,.0f}")
        if self.artifacts_path:
            lines.append(f"Artifacts : {self.artifacts_path}")
        if self.errors:
            lines.append(f"Errors    : {', '.join(self.errors)}")
        return "\n".join(lines)
