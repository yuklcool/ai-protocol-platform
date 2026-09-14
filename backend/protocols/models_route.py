"""Public platform metadata endpoints.

``GET /api/models`` serves the model registry used by the skill-settings UI.
``GET /api/capabilities`` exposes which provider backends are enabled so a
self-host can distinguish an intentionally-disabled optional cloud feature from
a broken service. Neither endpoint contains credentials or sensitive values.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from config.capabilities import capabilities_payload
from config.models import ModelEntry, load_models_config

router = APIRouter(prefix="/api", tags=["platform"])


class ModelsResponse(BaseModel):
    models: list[ModelEntry]
    defaults: dict[str, str]
    platform_default: str
    # v6.6.0: logical tier name -> registry id (e.g. {"lite": "gemini-flash-lite"}).
    tier_defaults: dict[str, str] = {}


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """Return all supported models grouped by provider."""
    cfg = load_models_config()
    return ModelsResponse(
        models=cfg.models,
        defaults=cfg.defaults,
        platform_default=cfg.platform_default,
        tier_defaults=cfg.tier_defaults,
    )


@router.get("/capabilities")
async def platform_capabilities() -> dict[str, object]:
    """Return provider/backend status without probing optional cloud services."""
    return capabilities_payload()
