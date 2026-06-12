"""Advanced cost optimization: Reserved Instances, Savings Plans, rightsizing."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReservationRecommendation:
    component: str          # e.g. "data_warehouse", "compute"
    current_tool: str       # e.g. "snowflake", "redshift"
    commitment_term: str    # "1yr" | "3yr"
    payment_option: str     # "no_upfront" | "partial_upfront" | "all_upfront"
    current_monthly_usd: float
    reserved_monthly_usd: float
    savings_pct: float
    annual_savings_usd: float
    break_even_months: int
    recommendation: str     # human-readable


@dataclass
class SavingsPlanRecommendation:
    plan_type: str          # "compute" | "ec2_instance" | "sagemaker"
    commitment_per_hour: float
    current_monthly_usd: float
    estimated_monthly_usd: float
    savings_pct: float
    recommendation: str


@dataclass
class CostOptimizationReport:
    total_current_monthly_usd: float
    total_optimized_monthly_usd: float
    total_annual_savings_usd: float
    optimization_score: int   # 0-100
    reserved_instance_recommendations: list[ReservationRecommendation] = field(default_factory=list)
    savings_plan_recommendations: list[SavingsPlanRecommendation] = field(default_factory=list)
    quick_wins: list[str] = field(default_factory=list)     # < 1 day effort
    medium_term: list[str] = field(default_factory=list)   # 1-7 days
    long_term: list[str] = field(default_factory=list)     # > 7 days


class CostOptimizer:
    """Generate Reserved Instance and Savings Plan recommendations."""

    # Discount rates for RI commitments (approximate AWS/GCP/Azure)
    _RI_DISCOUNTS = {
        "snowflake": {"1yr": 0.20, "3yr": 0.40},
        "redshift": {"1yr": 0.40, "3yr": 0.60},
        "bigquery": {"1yr": 0.0, "3yr": 0.0},   # BigQuery is on-demand
        "databricks": {"1yr": 0.15, "3yr": 0.30},
        "fivetran": {"1yr": 0.10, "3yr": 0.20},
        "airbyte": {"1yr": 0.0, "3yr": 0.0},   # open source
        "airflow": {"1yr": 0.30, "3yr": 0.50},  # MWAA
        "dagster": {"1yr": 0.15, "3yr": 0.25},
        "prefect": {"1yr": 0.15, "3yr": 0.25},
    }

    def analyze(self, stack: dict, monthly_costs: dict[str, float]) -> CostOptimizationReport:
        """
        Given a stack config and per-component monthly costs, generate optimization report.
        monthly_costs: {"data_warehouse": 400.0, "orchestrator": 150.0, ...}
        """
        reservations = []
        total_current = sum(monthly_costs.values())
        total_optimized = total_current

        for component, monthly_usd in monthly_costs.items():
            tool = stack.get(component, "")
            if not tool or monthly_usd <= 0:
                continue
            discounts = self._RI_DISCOUNTS.get(tool, {})
            if not discounts:
                continue

            for term, discount in discounts.items():
                if discount <= 0:
                    continue
                reserved_monthly = monthly_usd * (1 - discount)
                annual_savings = (monthly_usd - reserved_monthly) * 12
                break_even = int(1 / discount) if discount > 0 else 99

                reservations.append(ReservationRecommendation(
                    component=component,
                    current_tool=tool,
                    commitment_term=term,
                    payment_option="partial_upfront",
                    current_monthly_usd=monthly_usd,
                    reserved_monthly_usd=round(reserved_monthly, 2),
                    savings_pct=round(discount * 100, 1),
                    annual_savings_usd=round(annual_savings, 2),
                    break_even_months=break_even,
                    recommendation=f"Switch {tool} to {term} Reserved/Committed pricing — save {discount*100:.0f}% (${annual_savings:.0f}/yr)"
                ))
                total_optimized -= (monthly_usd - reserved_monthly)
                break  # just the best 1-yr option per component

        quick_wins = []
        medium_term = []
        long_term = []

        if stack.get("data_warehouse") in ("snowflake", "redshift"):
            quick_wins.append("Enable auto-suspend on warehouse (saves 40-60% on idle hours)")
        if stack.get("orchestrator") in ("airflow",):
            quick_wins.append("Use spot/preemptible instances for Airflow workers (save up to 70%)")
        if stack.get("bi_tool") in ("tableau", "looker"):
            medium_term.append("Consider Metabase or Superset as open-source BI alternative (eliminate BI license cost)")
        if stack.get("ingestion") in ("fivetran",):
            medium_term.append("Evaluate Airbyte (open-source) to eliminate Fivetran MAR costs")
        long_term.append("Implement data tiering: move cold data to S3/GCS cold storage (save 70% on storage)")
        long_term.append("Set up cost anomaly detection alerts with 10% threshold")

        savings_score = min(100, int((total_current - total_optimized) / max(total_current, 1) * 200))

        return CostOptimizationReport(
            total_current_monthly_usd=round(total_current, 2),
            total_optimized_monthly_usd=round(total_optimized, 2),
            total_annual_savings_usd=round((total_current - total_optimized) * 12, 2),
            optimization_score=savings_score,
            reserved_instance_recommendations=reservations,
            quick_wins=quick_wins,
            medium_term=medium_term,
            long_term=long_term,
        )
