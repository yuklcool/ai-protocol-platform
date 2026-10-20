from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from auth import get_current_user
from config.capabilities import capabilities_payload
from config.effective_models import EffectiveModelEntry, load_effective_models_config

router = APIRouter(prefix="/api", tags=["platform"])


class ModelsResponse(BaseModel):
    models: list[EffectiveModelEntry]
    defaults: dict[str, str]
    platform_default: str
    tier_defaults: dict[str, str] = {}


@router.get("/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    if request.headers.get("Authorization"):
        await get_current_user(request)
    cfg = load_effective_models_config()
    return ModelsResponse(
        models=cfg.models, defaults=cfg.defaults, platform_default=cfg.platform_default, tier_defaults=cfg.tier_defaults
    )


@router.get("/capabilities")
async def platform_capabilities() -> dict[str, object]:
    """Return provider/backend status without probing optional cloud services."""
    return capabilities_payload()
