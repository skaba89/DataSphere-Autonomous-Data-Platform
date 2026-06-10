from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datasphere.models.request import ArchitectureConstraints


class ArchitectureProposal(BaseModel):
    """One of 2-3 architecture proposals offered to the human."""
    id: int
    name: str
    tagline: str
    constraints: ArchitectureConstraints
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    estimated_monthly_usd: float = 0.0
    complexity: str = "medium"       # low | medium | high
    time_to_deploy: str = ""
    best_for: str = ""


class ConversationState(BaseModel):
    """Tracks where we are in the 5-step dialogue."""
    step: int = 1
    business_request: str = ""
    raw_constraints: dict = Field(default_factory=dict)
    proposals: list[ArchitectureProposal] = Field(default_factory=list)
    chosen_proposal: Optional[ArchitectureProposal] = None
    complete: bool = False
