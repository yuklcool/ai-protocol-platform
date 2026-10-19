"""Tenant onboarding/edit/disable API backed by the first-class tenant directory.

Phase 3 moves the admin plane away from ``clients/{domain}``.  The public API
stays backward-compatible with the historical single-domain request while also
supporting stable ``tenant_id`` values, multiple identity domains, domain-less
OIDC/JWT tenants, storage namespaces and per-tenant policy/quota metadata.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from admin.audit import record_admin_action
from admin.scope import AdminScope, require_admin_scope
from db.persistence import get_repository
from db.tenants import TenantConfig, TenantDirectory, normalize_domain, normalize_tenant_id
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tenants", tags=["admin-tenants"])

_LEVEL_OK = "ok"
_LEVEL_WARNING = "warning"
_LEVEL_ERROR = "error"
_LEVEL_SKIPPED = "skipped"


class ValidationCheck(BaseModel):
    field: str
    level: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TenantValidation(BaseModel):
    tenant_id: str
    ok: bool
    checks: list[ValidationCheck]


class TenantOnboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)

    display_name: str = ""
    enabled_skills: list[str] | None = None
    enabled_mcp_servers: list[str] | None = None
    default_skill: str | None = None

    model_policy: dict[str, Any] = Field(default_factory=dict)
    storage_namespace: str = ""
    quota: dict[str, Any] = Field(default_factory=dict)

    # Legacy GCS-specific setting remains optional. Self-host local storage
    # does not require it and never probes GCP merely because this route runs.
    documents_bucket: str | None = None
    disabled: bool = False


class TenantPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domains: list[str] | None = None
    display_name: str | None = None
    enabled_skills: list[str] | None = None
    enabled_mcp_servers: list[str] | None = None
    default_skill: str | None = None
    model_policy: dict[str, Any] | None = None
    storage_namespace: str | None = None
    quota: dict[str, Any] | None = None
    documents_bucket: str | None = None
    disabled: bool | None = None


class TenantOnboardResponse(BaseModel):
    tenant_id: str
    # Compatibility echo: first identity domain when present, else tenant_id.
    domain: str
    config: TenantConfig
    validation: TenantValidation


def _directory() -> TenantDirectory:
    return TenantDirectory(get_repository())


class TenantQuota(BaseModel):
    llmBudgetUsd: float = Field(default=0, ge=0, allow_inf_nan=False)
    llmBudgetSoftThreshold: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    llmBudgetPeriod: str = "monthly"


def _validate_admin_policy(scope: AdminScope, model_policy: dict | None, quota: dict | None) -> None:
    if model_policy is not None or quota is not None:
        scope.assert_platform()
    if quota:
        try:
            value = TenantQuota.model_validate(quota)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid tenant quota") from exc
        if value.llmBudgetPeriod not in {"daily", "weekly", "monthly"}:
            raise HTTPException(422, "Budget period must be daily, weekly or monthly")
    if model_policy:
        from config.effective_models import load_effective_models_config
        from config.tenant_models import TenantModelPolicy, validate_tenant_model_policy

        try:
            policy = TenantModelPolicy.model_validate(model_policy)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid tenant model policy") from exc
        errors = validate_tenant_model_policy(policy, (entry.id for entry in load_effective_models_config().models))
        if errors:
            raise HTTPException(422, {"error": "invalid_model_policy", "messages": errors})


@router.get("", response_model=list[TenantConfig])
def list_tenants(scope: Annotated[AdminScope, Depends(require_admin_scope)]) -> list[TenantConfig]:
    return [tenant for tenant in _directory().list() if scope.may_tenant(tenant.tenant_id)]


@router.get("/{tenant_id}", response_model=TenantConfig)
def read_tenant(tenant_id: str, scope: Annotated[AdminScope, Depends(require_admin_scope)]) -> TenantConfig:
    _assert_scope(scope, tenant_id)
    tenant = _directory().get(tenant_id)
    if tenant is None:
        raise HTTPException(404, "Tenant not found")
    return tenant


def _normalize_identity(body: TenantOnboardRequest) -> tuple[str, list[str]]:
    tenant_id = normalize_tenant_id(body.tenant_id)
    if not tenant_id:
        raise HTTPException(422, "tenant_id is required")
    domains = sorted({normalize_domain(value) for value in body.domains if normalize_domain(value)})
    return tenant_id, domains


def _assert_scope(scope: AdminScope, tenant_id: str) -> None:
    scope.assert_may_tenant(tenant_id)


def _known_slugs(actor_uid: str) -> set[str]:
    slugs: set[str] = set()
    for owner in (PLATFORM_OWNER_UID, actor_uid):
        if not owner:
            continue
        try:
            for cfg in skill_config.list_skills(owner_id=owner, limit=200):
                if cfg.slug:
                    slugs.add(cfg.slug)
        except Exception as exc:
            log.info("tenant validate: could not list skills for owner %s: %s", owner, exc)
    return slugs


def _validate_resource_scope(tenant_id: str, skills: list[str] | None, servers: list[str] | None) -> None:
    for ref in skills or []:
        skill = skill_config.get_skill(ref)
        if skill is None or not (
            skill.tenant_id == tenant_id or (not skill.tenant_id and skill.owner_id == PLATFORM_OWNER_UID)
        ):
            raise HTTPException(422, "Skill 不存在或不属于目标租户")
    for ref in servers or []:
        server = get_repository().get_document("mcp_servers", ref)
        if not server or not (
            server.get("scope") == "platform"
            or (server.get("scope") == "tenant" and server.get("tenantId") == tenant_id)
        ):
            raise HTTPException(422, "MCP 服务器不存在或不属于目标租户")


def unknown_skill_refs(
    enabled_skills: list[str] | None,
    default_skill: str | None,
    actor_uid: str,
) -> list[str]:
    refs = [value for value in list(enabled_skills or []) if value]
    if default_skill:
        refs.append(default_skill)
    if not refs:
        return []
    known = _known_slugs(actor_uid)
    unknown: list[str] = []
    seen: set[str] = set()
    for value in refs:
        if value not in known and skill_config.get_skill(value) is None and value not in seen:
            unknown.append(value)
            seen.add(value)
    return unknown


def _validate_skill_refs(
    enabled_skills: list[str] | None,
    default_skill: str | None,
    actor_uid: str,
) -> list[ValidationCheck]:
    unknown = set(unknown_skill_refs(enabled_skills, default_skill, actor_uid))
    checks: list[ValidationCheck] = []

    enabled = [skill for skill in (enabled_skills or []) if skill]
    bad_enabled = [skill for skill in enabled if skill in unknown]
    if not enabled:
        checks.append(
            ValidationCheck(
                field="enabled_skills",
                level=_LEVEL_OK,
                message="No enabled-skills filter (all skills visible).",
            )
        )
    elif bad_enabled:
        checks.append(
            ValidationCheck(
                field="enabled_skills",
                level=_LEVEL_ERROR,
                message=f"Unknown skill slug(s): {', '.join(bad_enabled)}",
                details={"unknown": bad_enabled},
            )
        )
    else:
        checks.append(
            ValidationCheck(
                field="enabled_skills",
                level=_LEVEL_OK,
                message=f"All {len(enabled)} enabled skill(s) resolved.",
                details={"skills": enabled},
            )
        )

    if default_skill:
        if default_skill in unknown:
            checks.append(
                ValidationCheck(
                    field="default_skill",
                    level=_LEVEL_ERROR,
                    message=f"Unknown default skill slug: {default_skill}",
                    details={"unknown": [default_skill]},
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    field="default_skill",
                    level=_LEVEL_OK,
                    message=f"Landing skill {default_skill!r} resolved.",
                    details={"skill": default_skill},
                )
            )
    else:
        checks.append(
            ValidationCheck(
                field="default_skill",
                level=_LEVEL_OK,
                message="No landing skill set (marketplace default).",
            )
        )
    return checks


def _gcs_selected() -> bool:
    artifact = os.environ.get("ARTIFACT_BACKEND", "").strip().lower()
    objects = os.environ.get("OBJECT_STORAGE_BACKEND", "").strip().lower()
    return artifact == "gcs" or objects == "gcs"


def _validate_storage(config: TenantConfig) -> ValidationCheck:
    if not _gcs_selected():
        return ValidationCheck(
            field="storage_namespace",
            level=_LEVEL_OK,
            message="Provider-neutral/local tenant storage namespace is configured.",
            details={"storageNamespace": config.storage_namespace},
        )

    bucket = (config.documents_bucket or "").strip()
    if not bucket:
        return ValidationCheck(
            field="documents_bucket",
            level=_LEVEL_WARNING,
            message="GCS backend is selected but this tenant has no documents bucket.",
        )

    # GCP import is intentionally lazy and only happens when a GCS backend was
    # explicitly selected. SELF_HOSTED_MODE with local storage never touches
    # Google credentials here.
    try:
        from google.api_core.exceptions import Forbidden, NotFound
        from google.cloud import storage

        client = storage.Client()
        next(iter(client.list_blobs(bucket, max_results=1)), None)
        return ValidationCheck(
            field="documents_bucket",
            level=_LEVEL_OK,
            message=f"Bucket {bucket!r} is reachable.",
            details={"bucket": bucket, "exists": True, "readable": True},
        )
    except NotFound:
        return ValidationCheck(
            field="documents_bucket",
            level=_LEVEL_WARNING,
            message=f"Bucket {bucket!r} was not found.",
            details={"bucket": bucket, "exists": False, "readable": False},
        )
    except Forbidden:
        return ValidationCheck(
            field="documents_bucket",
            level=_LEVEL_WARNING,
            message=f"Bucket {bucket!r} exists but is not readable by this runtime.",
            details={"bucket": bucket, "exists": True, "readable": False},
        )
    except Exception as exc:
        log.info("tenant storage validation skipped for %s: %s", bucket, exc)
        return ValidationCheck(
            field="documents_bucket",
            level=_LEVEL_SKIPPED,
            message=f"Could not verify GCS bucket {bucket!r}; runtime credentials are unavailable.",
            details={"bucket": bucket},
        )


def build_validation(config: TenantConfig, *, actor_uid: str) -> TenantValidation:
    checks: list[ValidationCheck] = []
    checks.extend(_validate_skill_refs(config.enabled_skills, config.default_skill, actor_uid))
    checks.append(_validate_storage(config))
    ok = not any(check.level == _LEVEL_ERROR for check in checks)
    return TenantValidation(tenant_id=config.tenant_id, ok=ok, checks=checks)


def _audit_config(config: TenantConfig | None) -> dict[str, Any] | None:
    return config.model_dump(by_alias=True, exclude_none=True) if config else None


@router.post("", response_model=TenantOnboardResponse, status_code=201)
def onboard_tenant(
    body: TenantOnboardRequest,
    scope: Annotated[AdminScope, Depends(require_admin_scope)],
) -> TenantOnboardResponse:
    tenant_id, domains = _normalize_identity(body)
    _assert_scope(scope, tenant_id)
    _validate_admin_policy(
        scope,
        body.model_policy if "model_policy" in body.model_fields_set else None,
        body.quota if "quota" in body.model_fields_set else None,
    )

    unknown = unknown_skill_refs(body.enabled_skills, body.default_skill, scope.user.uid)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_skill_ref",
                "unknown": unknown,
                "message": f"Unknown skill slug(s): {', '.join(unknown)}",
            },
        )

    _validate_resource_scope(tenant_id, body.enabled_skills, body.enabled_mcp_servers)
    directory = _directory()
    if directory.get(tenant_id) is not None:
        raise HTTPException(status_code=409, detail=f"Tenant {tenant_id!r} already exists")

    config = TenantConfig(
        tenantId=tenant_id,
        displayName=body.display_name.strip(),
        domains=domains,
        enabledSkills=body.enabled_skills or [],
        defaultSkill=(body.default_skill or "").strip() or None,
        enabledMcpServers=body.enabled_mcp_servers or [],
        modelPolicy=body.model_policy,
        storageNamespace=body.storage_namespace.strip() or tenant_id,
        documentsBucket=(body.documents_bucket or "").strip() or None,
        quota=body.quota,
        disabled=body.disabled,
    ).normalized()

    validation = build_validation(config, actor_uid=scope.user.uid)
    if not validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tenant_validation_failed",
                "checks": [check.model_dump() for check in validation.checks],
            },
        )

    try:
        saved = directory.put(config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="onboard_tenant",
        target=saved.tenant_id,
        tenant_id=saved.tenant_id,
        before=None,
        after=_audit_config(saved),
    )
    log.info("admin.tenants: onboard tenant=%s by uid=%s", saved.tenant_id, scope.user.uid)

    return TenantOnboardResponse(
        tenant_id=saved.tenant_id,
        domain=saved.domains[0] if saved.domains else saved.tenant_id,
        config=saved,
        validation=validation,
    )


@router.patch("/{tenant_id}", response_model=TenantConfig)
def edit_tenant(
    tenant_id: str,
    body: TenantPatchRequest,
    scope: Annotated[AdminScope, Depends(require_admin_scope)],
) -> TenantConfig:
    tenant_id = normalize_tenant_id(tenant_id)
    _assert_scope(scope, tenant_id)
    if body.model_policy is not None or body.quota is not None:
        scope.assert_platform()
    _validate_admin_policy(scope, body.model_policy, body.quota)
    directory = _directory()
    current = directory.get(tenant_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id!r} not found")

    updates: dict[str, Any] = {}
    if body.domains is not None:
        updates["domains"] = [normalize_domain(value) for value in body.domains if normalize_domain(value)]
    if body.display_name is not None:
        updates["display_name"] = body.display_name.strip()
    if body.enabled_skills is not None:
        updates["enabled_skills"] = body.enabled_skills
    if body.enabled_mcp_servers is not None:
        updates["enabled_mcp_servers"] = body.enabled_mcp_servers
    if body.default_skill is not None:
        updates["default_skill"] = body.default_skill.strip() or None
    if body.model_policy is not None:
        updates["model_policy"] = body.model_policy
    if body.storage_namespace is not None:
        updates["storage_namespace"] = body.storage_namespace.strip() or tenant_id
    if body.quota is not None:
        updates["quota"] = body.quota
    if body.documents_bucket is not None:
        updates["documents_bucket"] = body.documents_bucket.strip() or None
    if body.disabled is not None:
        updates["disabled"] = body.disabled

    candidate = current.model_copy(update=updates).normalized()
    unknown = unknown_skill_refs(candidate.enabled_skills, candidate.default_skill, scope.user.uid)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"error": "unknown_skill_ref", "unknown": unknown},
        )

    _validate_resource_scope(tenant_id, body.enabled_skills, body.enabled_mcp_servers)
    validation = build_validation(candidate, actor_uid=scope.user.uid)
    if not validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tenant_validation_failed",
                "checks": [check.model_dump() for check in validation.checks],
            },
        )

    try:
        saved = directory.put(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="edit_tenant",
        target=saved.tenant_id,
        tenant_id=saved.tenant_id,
        before=_audit_config(current),
        after=_audit_config(saved),
    )
    return saved


@router.post("/{tenant_id}/disable", response_model=TenantConfig)
def disable_tenant(
    tenant_id: str,
    scope: Annotated[AdminScope, Depends(require_admin_scope)],
) -> TenantConfig:
    tenant_id = normalize_tenant_id(tenant_id)
    _assert_scope(scope, tenant_id)
    directory = _directory()
    current = directory.get(tenant_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id!r} not found")
    saved = directory.set_disabled(tenant_id, True)
    assert saved is not None
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="disable_tenant",
        target=saved.tenant_id,
        tenant_id=saved.tenant_id,
        before=_audit_config(current),
        after=_audit_config(saved),
    )
    return saved


@router.post("/{tenant_id}/enable", response_model=TenantConfig)
def enable_tenant(
    tenant_id: str,
    scope: Annotated[AdminScope, Depends(require_admin_scope)],
) -> TenantConfig:
    tenant_id = normalize_tenant_id(tenant_id)
    _assert_scope(scope, tenant_id)
    directory = _directory()
    current = directory.get(tenant_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id!r} not found")
    saved = directory.set_disabled(tenant_id, False)
    assert saved is not None
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="enable_tenant",
        target=saved.tenant_id,
        tenant_id=saved.tenant_id,
        before=_audit_config(current),
        after=_audit_config(saved),
    )
    return saved


@router.get("/{tenant_id}/validate", response_model=TenantValidation)
def validate_tenant(
    tenant_id: str,
    scope: Annotated[AdminScope, Depends(require_admin_scope)],
) -> TenantValidation:
    tenant_id = normalize_tenant_id(tenant_id)
    _assert_scope(scope, tenant_id)
    stored = _directory().get(tenant_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id!r} not found")
    return build_validation(stored, actor_uid=scope.user.uid)
