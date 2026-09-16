"""Platform-admin management for per-tenant model access policy.

Policies live on first-class ``tenants/{tenant_id}.modelPolicy`` documents.  The
route intentionally refuses to mutate a legacy ``clients/{domain}`` bridge:
legacy ownership must be migrated explicitly under #9 rather than being
silently converted as a side effect of model administration.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import PlatformScope
from config.effective_models import load_effective_models_config
from config.tenant_models import TenantModelPolicy, validate_tenant_model_policy
from db.persistence import get_repository
from db.tenants import TENANT_COLLECTION, TenantDirectory, normalize_tenant_id

router = APIRouter(prefix="/tenant-model-policies", tags=["admin-tenant-model-policy"])


class TenantModelPolicyWrite(BaseModel):
    allowed_models: list[str] | None = None
    default_model: str | None = None


class TenantModelOption(BaseModel):
    model_id: str
    api_name: str
    provider: str
    tier: str
    residency: str
    source: str
    allowed: bool


class TenantModelPolicyView(BaseModel):
    tenant_id: str
    allowed_models: list[str] | None
    default_model: str | None
    effective_default_model: str | None
    available_models: list[TenantModelOption]


def _load_first_class_tenant(tenant_id: str):
    stable_id = normalize_tenant_id(tenant_id)
    if not stable_id:
        raise HTTPException(status_code=422, detail="tenant_id must be non-empty")
    repository = get_repository()
    if repository.get_document(TENANT_COLLECTION, stable_id) is None:
        # TenantDirectory.get() may synthesize a legacy clients/{domain}
        # compatibility view. Refuse to write through that bridge here.
        if TenantDirectory(repository).get(stable_id) is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Tenant still uses legacy domain ownership. Migrate it to a first-class tenant "
                    "before assigning model policy."
                ),
            )
        raise HTTPException(status_code=404, detail=f"Tenant {stable_id!r} not found")
    tenant = TenantDirectory(repository).get(stable_id)
    if tenant is None:  # Defensive: first-class document existed but was invalid/unreadable.
        raise HTTPException(status_code=404, detail=f"Tenant {stable_id!r} not found")
    return repository, tenant


def _effective_default(policy: TenantModelPolicy, model_ids: set[str], platform_default: str, tier_default: str | None) -> str | None:
    if policy.default_model:
        return policy.default_model if policy.default_model in model_ids and policy.allows(policy.default_model) else None
    candidate = tier_default or platform_default
    return candidate if candidate in model_ids and policy.allows(candidate) else None


def _view(tenant_id: str) -> TenantModelPolicyView:
    _, tenant = _load_first_class_tenant(tenant_id)
    cfg = load_effective_models_config()
    policy = TenantModelPolicy.model_validate(tenant.model_policy or {})
    model_ids = {entry.id for entry in cfg.models}
    return TenantModelPolicyView(
        tenant_id=tenant.tenant_id,
        allowed_models=policy.allowed_models,
        default_model=policy.default_model,
        effective_default_model=_effective_default(
            policy,
            model_ids,
            cfg.platform_default,
            cfg.tier_defaults.get("default"),
        ),
        available_models=[
            TenantModelOption(
                model_id=entry.id,
                api_name=entry.api_name,
                provider=entry.provider,
                tier=entry.tier,
                residency=entry.residency,
                source=entry.source,
                allowed=policy.allows(entry.id),
            )
            for entry in cfg.models
        ],
    )


@router.get("/{tenant_id}", response_model=TenantModelPolicyView)
def get_tenant_model_policy(tenant_id: str, scope: PlatformScope) -> TenantModelPolicyView:
    return _view(tenant_id)


@router.put("/{tenant_id}", response_model=TenantModelPolicyView)
def update_tenant_model_policy(
    tenant_id: str,
    body: TenantModelPolicyWrite,
    scope: PlatformScope,
) -> TenantModelPolicyView:
    repository, tenant = _load_first_class_tenant(tenant_id)
    cfg = load_effective_models_config()
    policy = TenantModelPolicy(
        allowedModels=body.allowed_models,
        defaultModel=body.default_model,
    )
    errors = validate_tenant_model_policy(policy, (entry.id for entry in cfg.models))
    if errors:
        raise HTTPException(status_code=422, detail={"error": "invalid_model_policy", "messages": errors})

    before = tenant.model_dump(by_alias=True, exclude_none=True)
    updated = tenant.model_copy(
        update={"model_policy": policy.model_dump(by_alias=True, exclude_none=True)}
    )
    saved = TenantDirectory(repository).put(updated)
    after = saved.model_dump(by_alias=True, exclude_none=True)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="update_tenant_model_policy",
        target=saved.tenant_id,
        tenant_id=saved.tenant_id,
        before=before,
        after=after,
    )
    return _view(saved.tenant_id)


__all__ = ["router"]
