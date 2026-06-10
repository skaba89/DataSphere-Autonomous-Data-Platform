from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AdapterConfig:
    host: str = "localhost"
    port: int = 0
    username: str = ""
    password: str = ""
    database: str = ""
    extra: dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


class BaseAdapter(ABC):
    name: str = ""
    category: str = ""

    def __init__(self, config: AdapterConfig):
        self.config = config

    @abstractmethod
    def connect(self) -> Any:
        """Return a live connection/client."""

    @abstractmethod
    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""

    @abstractmethod
    def deploy(self) -> str:
        """Return docker-compose/terraform snippet for this service."""

    def status(self) -> dict[str, Any]:
        """Return health/status information."""
        return {"adapter": self.name, "status": "unknown"}

    def teardown(self) -> None:
        """Clean up resources."""
