"""Public platform metadata endpoints.

``GET /api/models`` serves the effective model registry used by the
skill-settings UI. YAML remains the bootstrap/GitOps baseline; enabled dynamic
models from the persisted provider registry are overlaid when configured.
Authenticated tenant requests are additionally filtered through the tenant's
server-side model allow-list. Anonymous callers retain the historical public
metadata view for CLI/bootstrap compatibility.

``GET /api/capabilities`` exposes which provider backends are enabled so a
self-host can distinguish an intentionally-disabled optional cloud feature from
a broken service. Neither endpoint contains credentials or sensitive values.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from auth import get_current_user
from config.capabilities import capabilities_payload
from config.effective_models import EffectiveModelEntry, load_effective_models_config
from config.tenant_models import TenantModelPolicy, load_tenant_model_policy, tenant_id_for_user

router = APIRouter(prefix="/api", tags=["platform"])


class ModelsResponse(BaseModel):
    models: list[EffectiveModelEntry]
    defaults: dict[str, str]
    platform_default: str
    tier_defaults: dict[str, str] = {}


async def _request_tenant_id(request: Request) -> str:
    """Authenticate only when the caller supplied credentials.

    ``/api/models`` predates authenticated tenant metadata and is also used by
    public CLI/bootstrap flows. Keeping anonymous metadata compatible avoids an
    auth-breaking change, while an invalid supplied credential still fails via
    the normal authentication provider.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return ""
    user = await get_current_user(request)
    return tenant_id_for_user(user)


def _tenant_filtered_response(tenant_id: str) -> ModelsResponse:
    cfg = load_effective_models_config()
    policy = load_tenant_model_policy(tenant_id) if tenant_id else TenantModelPolicy()
    visible_models = [entry for entry in cfg.models if policy.allows(entry.id)]
    visible_ids = {entry.id for entry in visible_models}

    defaults = {provider: model_id for provider, model_id in cfg.defaults.items() if model_id in visible_ids}
    tier_defaults = {tier: model_id for tier, model_id in cfg.tier_defaults.items() if model_id in visible_ids}

    platform_default = cfg.platform_default if cfg.platform_default in visible_ids else ""
    if policy.default_model and policy.default_model in visible_ids:
        platform_default = policy.default_model
        tier_defaults["default"] = policy.default_model

    return ModelsResponse(
        models=visible_models,
        defaults=defaults,
        platform_default=platform_default,
        tier_defaults=tier_defaults,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """Return effective models, tenant-filtered for authenticated callers."""
    tenant_id = await _request_tenant_id(request)
    return _tenant_filtered_response(tenant_id)


@router.get("/capabilities")
async def platform_capabilities() -> dict[str, object]:
    """Return provider/backend status without probing optional cloud services."""
    return capabilities_payload()
