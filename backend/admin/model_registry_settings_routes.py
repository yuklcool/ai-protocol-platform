"""Platform-admin management for effective model defaults and tier aliases.

YAML remains the bootstrap/GitOps baseline. In database registry mode this
endpoint persists only model *references* in ``model_registry_settings`` and the
effective registry overlays them at read time, so Skill Studio and Agent runtime
observe the same mapping without a process restart.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import PlatformScope
from config.effective_models import MANAGED_TIER_NAMES, EffectiveModelEntry, load_effective_models_config
from config.model_provider_registry import SETTINGS_COLLECTION, database_registry_enabled, registry_settings
from db.persistence import get_document, set_document

router = APIRouter(prefix="/model-registry", tags=["admin-model-registry"])


class TierMapping(BaseModel):
    default: str = ""
    smart: str = ""
    fast: str = ""

    def normalized(self) -> dict[str, str]:
        return {tier: str(getattr(self, tier)).strip() for tier in MANAGED_TIER_NAMES}


class ModelRegistrySettingsWrite(BaseModel):
    platform_default: str
    tier_defaults: TierMapping


class ModelOption(BaseModel):
    model_id: str
    api_name: str
    provider: str
    provider_id: str | None = None
    tier: Literal["default", "smart", "fast"]
    residency: Literal["eu", "us", "global"]
    source: str


class ModelRegistrySettingsView(BaseModel):
    platform_default: str
    tier_defaults: TierMapping
    available_models: list[ModelOption]
    source: Literal["yaml", "database"]
    writable: bool


def _option(entry: EffectiveModelEntry) -> ModelOption:
    return ModelOption(
        model_id=entry.id,
        api_name=entry.api_name,
        provider=entry.provider,
        provider_id=entry.provider_id,
        tier=entry.tier,
        residency=entry.residency,
        source=entry.source,
    )


def _view() -> ModelRegistrySettingsView:
    cfg = load_effective_models_config()
    stored = registry_settings()
    return ModelRegistrySettingsView(
        platform_default=cfg.platform_default,
        tier_defaults=TierMapping(
            default=cfg.tier_defaults.get("default", ""),
            smart=cfg.tier_defaults.get("smart", ""),
            fast=cfg.tier_defaults.get("fast", ""),
        ),
        available_models=[_option(entry) for entry in cfg.models],
        source="database" if stored else "yaml",
        writable=database_registry_enabled(),
    )


@router.get("/settings", response_model=ModelRegistrySettingsView)
def get_model_registry_settings(scope: PlatformScope) -> ModelRegistrySettingsView:
    return _view()


@router.put("/settings", response_model=ModelRegistrySettingsView)
def update_model_registry_settings(
    body: ModelRegistrySettingsWrite,
    scope: PlatformScope,
) -> ModelRegistrySettingsView:
    if not database_registry_enabled():
        raise HTTPException(
            status_code=409,
            detail="Model registry is in YAML/GitOps mode; switch MODEL_REGISTRY_BACKEND=database to manage defaults here",
        )

    cfg = load_effective_models_config()
    available = {entry.id for entry in cfg.models}
    platform_default = body.platform_default.strip()
    tiers = body.tier_defaults.normalized()

    missing_fields = ["platform_default"] if not platform_default else []
    missing_fields.extend(f"tier_defaults.{tier}" for tier, target in tiers.items() if not target)
    if missing_fields:
        raise HTTPException(status_code=422, detail=f"Missing model mapping: {', '.join(missing_fields)}")

    requested = {platform_default, *tiers.values()}
    unknown = sorted(requested - available)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown or disabled model id(s): {', '.join(unknown)}",
        )

    before = get_document(SETTINGS_COLLECTION, "default")
    data = {
        "platformDefault": platform_default,
        "tierDefaults": tiers,
    }
    set_document(SETTINGS_COLLECTION, "default", data, merge=False)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="update_model_registry_settings",
        target="default",
        before=before,
        after=data,
    )
    return _view()


__all__ = ["router"]
