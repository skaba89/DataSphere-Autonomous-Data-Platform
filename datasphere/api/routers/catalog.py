"""Catalog routes: /stacks/supported, /stacks/adapters."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["catalog"])


@router.get("/stacks/supported", tags=["catalog"])
def supported_stacks() -> dict:
    """Retourne tous les outils supportés par catégorie."""
    from datasphere.core.config import ALLOWED
    return {"categories": ALLOWED}


@router.get("/stacks/adapters", tags=["catalog"])
def list_adapters() -> dict:
    """Retourne tous les adaptateurs enregistrés dans le registry."""
    from datasphere.core.registry import registry
    adapters: dict[str, list[str]] = {}
    for (category, name) in registry._registry:
        adapters.setdefault(category, []).append(name)
    return {"adapter_count": len(registry._registry), "adapters": adapters}
