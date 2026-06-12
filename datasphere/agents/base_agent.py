from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from datasphere.models.request import BusinessRequest
from datasphere.models.output import AgentOutput


class BaseAgent(ABC):
    """
    Base class for all DataSphere agents.
    Each agent receives the full BusinessRequest and the outputs
    of previously-run agents (context), then produces an AgentOutput.
    """

    name: str = "base"
    description: str = ""

    def run(self, request: BusinessRequest, context: dict[str, AgentOutput] | None = None) -> AgentOutput:
        ctx = context or {}
        try:
            return self._run(request, ctx)
        except Exception as exc:
            output = AgentOutput(agent=self.name, success=False)
            output.errors.append(f"{type(exc).__name__}: {exc}")
            return output

    @abstractmethod
    def _run(self, request: BusinessRequest, context: dict[str, AgentOutput]) -> AgentOutput:
        """Implement agent logic here."""

    def _constraints(self, request: BusinessRequest):
        return request.architecture_constraints
