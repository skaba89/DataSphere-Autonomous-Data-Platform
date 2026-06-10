from __future__ import annotations
from typing import Type
from datasphere.adapters.base import BaseAdapter


class AdapterRegistry:
    _registry: dict[tuple[str, str], Type[BaseAdapter]] = {}

    @classmethod
    def register(cls, category: str, name: str):
        def decorator(adapter_cls: Type[BaseAdapter]):
            cls._registry[(category, name)] = adapter_cls
            return adapter_cls
        return decorator

    @classmethod
    def get(cls, category: str, name: str) -> Type[BaseAdapter]:
        key = (category, name)
        if key not in cls._registry:
            raise KeyError(f"No adapter registered for {category}/{name}")
        return cls._registry[key]

    @classmethod
    def list_adapters(cls, category: str | None = None) -> list[tuple[str, str]]:
        if category:
            return [k for k in cls._registry if k[0] == category]
        return list(cls._registry.keys())


registry = AdapterRegistry()
