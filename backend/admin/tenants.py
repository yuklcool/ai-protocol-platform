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
from pydantic import BaseModel, Field

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
    # New first-class identity. Omitted for old callers: ``domain`` becomes
    # the stable id until the tenant is explicitly migrated.
    tenant_id: str = ""
    domains: list[str] = Field(default_factory=list)

    # Historical single-domain field retained for frontend/API compatibility.
    domain: str = ""

    display_name: str = ""
    enabled_skills: list[str] | None = None
    derived_group_tags: list[str] | None = None
    default_skill: str | None = None

    model_policy: dict[str, Any] = Field(default_factory=dict)
    storage_namespace: str = ""
    quota: dict[str, Any] = Field(default_factory=dict)

    # Legacy GCS-specific setting remains optional. Self-host local storage
    # does not require it and never probes GCP merely because this route runs.
    documents_bucket: str | None = None
    disabled: bool = False


class TenantPatchRequest(BaseModel):
    domains: list[str] | None = None
    display_name: str | None = None
    enabled_skills: list[str] | None = None
    derived_group_tags: list[str] | None = None
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


def _normalize_identity(body: TenantOnboardRequest) -> tuple[str, list[str]]:
    legacy_domain = normalize_domain(body.domain)
    domains = [normalize_domain(value) for value in body.domains]
    if legacy_domain:
        domains.append(legacy_domain)
    domains = sorted({value for value in domains if value})

    tenant_id = normalize_tenant_id(body.tenant_id)
    if not tenant_id:
        if legacy_domain:
            tenant_id = legacy_domain
        elif len(domains) == 1:
            tenant_id = domains[0]

    if not tenant_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "tenant_id is required when no legacy domain is supplied. "
                "Domain-less OIDC/JWT tenants are supported; give them a stable tenant_id."
            ),
        )
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
    # Preserve the historical fail-open behavior when a provider cannot list
    # skills; onboarding must not become unavailable because validation storage
    # is temporarily down.
    if not known:
        return []
    unknown: list[str] = []
    seen: set[str] = set()
    for value in refs:
        if value not in known and value not in seen:
            unknown.append(value)
            seen.add(value)
    return unknown


def _known_group_tags() -> set[str] | None:
    try:
        from auth import group_tags_registry  # type: ignore[attr-defined]
    except Exception:
        return None
    fn = getattr(group_tags_registry, "known_group_tags", None)
    if not callable(fn):
        return None
    try:
        return set(fn())
    except Exception:
        return None


def _validate_group_tags(tags: list[str] | None) -> ValidationCheck:
    cleaned = [tag for tag in (tags or []) if tag]
    registry = _known_group_tags()
    if registry is None:
        return ValidationCheck(
            field="derived_group_tags",
            level=_LEVEL_SKIPPED,
            message=(
                "No group-tag registry in this build; accepting tags without validation."
                if cleaned
                else "No derived group tags."
            ),
            details={"tags": cleaned},
        )
    unknown = [tag for tag in cleaned if tag not in registry]
    if unknown:
        return ValidationCheck(
            field="derived_group_tags",
            level=_LEVEL_ERROR,
            message=f"Unknown group tag(s): {', '.join(unknown)}",
            details={"unknown": unknown},
        )
    return ValidationCheck(
        field="derived_group_tags",
        level=_LEVEL_OK,
        message="All derived group tags are recognized." if cleaned else "No derived group tags.",
        details={"tags": cleaned},
    )


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
    checks.append(_validate_group_tags(config.derived_group_tags))
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

    directory = _directory()
    if directory.get(tenant_id) is not None:
        raise HTTPException(status_code=409, detail=f"Tenant {tenant_id!r} already exists")

    config = TenantConfig(
        tenantId=tenant_id,
        displayName=body.display_name.strip(),
        domains=domains,
        enabledSkills=body.enabled_skills or None,
        defaultSkill=(body.default_skill or "").strip() or None,
        derivedGroupTags=body.derived_group_tags or None,
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
        actor_email=scope.user.email or "",
        action="onboard_tenant",
        target=saved.tenant_id,
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
        updates["enabled_skills"] = body.enabled_skills or None
    if body.derived_group_tags is not None:
        updates["derived_group_tags"] = body.derived_group_tags or None
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
        actor_email=scope.user.email or "",
        action="edit_tenant",
        target=saved.tenant_id,
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
        actor_email=scope.user.email or "",
        action="disable_tenant",
        target=saved.tenant_id,
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
        actor_email=scope.user.email or "",
        action="enable_tenant",
        target=saved.tenant_id,
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
