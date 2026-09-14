"""Tenant onboarding + validation API (v6.9.0 / 9.4).

Adds an orchestration layer on top of the pass-through client CRUD in
``admin/clients.py``:

  * ``POST /api/admin/tenants`` — **atomic onboard**. Validates the proposed
    tenant config, and only writes ``clients/{domain}`` if the hard checks pass
    (unknown skill ref -> 422 BEFORE any write). Non-blocking checks (bucket
    reachability, group tags) return WARNING verdicts alongside the created
    config so the onboarding UI can surface them.
  * ``GET  /api/admin/tenants/{domain}/validate`` — dry-run over the STORED
    config for an existing tenant (the editor's "re-validate" button).

Tenant records are persisted through ``db.persistence`` so the existing
client/domain tenant model works unchanged on memory, Firestore, or PostgreSQL.
Object-storage reachability remains a provider-specific validation concern.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import resolve_admin_scope
from auth import User, get_current_user
from db.clients import ClientConfig, get_client_sync, invalidate_client_cache
from db.persistence import get_document, set_document
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tenants", tags=["admin-tenants"])

_COLLECTION = "clients"
_LEVEL_OK = "ok"
_LEVEL_WARNING = "warning"
_LEVEL_ERROR = "error"
_LEVEL_SKIPPED = "skipped"


class ValidationCheck(BaseModel):
    field: str
    level: str
    message: str
    details: dict[str, Any] = {}


class TenantValidation(BaseModel):
    domain: str
    ok: bool
    checks: list[ValidationCheck]


class TenantOnboardRequest(BaseModel):
    domain: str
    display_name: str = ""
    documents_bucket: str | None = None
    enabled_skills: list[str] | None = None
    derived_group_tags: list[str] | None = None
    default_skill: str | None = None


class TenantOnboardResponse(BaseModel):
    domain: str
    config: ClientConfig
    validation: TenantValidation


def _require_tenant_admin(user: User, domain: str) -> None:
    scope = resolve_admin_scope(user)
    if scope is None or not scope.may(domain):
        raise HTTPException(
            status_code=403,
            detail=f"tenant-admin for {domain!r} (or aitana-admin) required",
        )


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
    refs = [r for r in list(enabled_skills or []) if r]
    if default_skill:
        refs.append(default_skill)
    refs = [r for r in refs if r]
    if not refs:
        return []
    known = _known_slugs(actor_uid)
    if not known:
        return []
    unknown: list[str] = []
    seen: set[str] = set()
    for r in refs:
        if r not in known and r not in seen:
            unknown.append(r)
            seen.add(r)
    return unknown


def _storage_client() -> Any:
    from google.cloud import storage

    return storage.Client()


def probe_bucket(bucket_name: str) -> dict[str, Any]:
    """Reachability probe using the runtime service account.

    This remains GCS-specific for the legacy cloud deployment. Self-host object
    storage abstraction is handled separately by the object-storage milestone;
    tenant metadata persistence itself is already provider-neutral here.
    """
    from google.api_core.exceptions import Forbidden, NotFound

    result: dict[str, Any] = {
        "bucket": bucket_name,
        "exists": False,
        "readable": False,
        "checked": False,
    }
    if not bucket_name:
        return result
    try:
        client = _storage_client()
        next(iter(client.list_blobs(bucket_name, max_results=1)), None)
        result.update(exists=True, readable=True, checked=True)
    except NotFound:
        result["checked"] = True
    except Forbidden as exc:
        result.update(exists=True, checked=True)
        log.info("probe_bucket: %s exists but is unreadable by the SA: %s", bucket_name, exc)
    except Exception as exc:
        log.info("probe_bucket: %s not reachable: %s", bucket_name, exc)
    return result


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
    cleaned = [t for t in (tags or []) if t]
    registry = _known_group_tags()
    if registry is None:
        msg = (
            "No group-tag registry in this build; accepting tags without validation."
            if cleaned
            else "No derived group tags."
        )
        return ValidationCheck(
            field="derived_group_tags",
            level=_LEVEL_SKIPPED,
            message=msg,
            details={"tags": cleaned},
        )
    unknown = [t for t in cleaned if t not in registry]
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

    enabled = [s for s in (enabled_skills or []) if s]
    bad_enabled = [s for s in enabled if s in unknown]
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


def _validate_bucket(documents_bucket: str | None) -> ValidationCheck | None:
    if not documents_bucket:
        return None
    probe = probe_bucket(documents_bucket)
    details = {
        "bucket": documents_bucket,
        "exists": bool(probe.get("exists")),
        "readable": bool(probe.get("readable")),
    }
    if not probe.get("checked"):
        msg = f"Could not verify bucket {documents_bucket!r} reachability (SA/creds unavailable)."
    elif probe.get("exists") and probe.get("readable"):
        msg = f"Bucket {documents_bucket!r} is reachable by the service account."
        return ValidationCheck(
            field="documents_bucket", level=_LEVEL_OK, message=msg, details=details
        )
    elif probe.get("exists"):
        msg = (
            f"Bucket {documents_bucket!r} exists but the service account cannot read it "
            "(grant roles/storage.objectViewer)."
        )
    else:
        msg = f"Bucket {documents_bucket!r} does not exist or is not visible to the service account."
    return ValidationCheck(
        field="documents_bucket", level=_LEVEL_WARNING, message=msg, details=details
    )


def build_validation(
    *,
    domain: str,
    enabled_skills: list[str] | None,
    default_skill: str | None,
    documents_bucket: str | None,
    derived_group_tags: list[str] | None,
    actor_uid: str,
) -> TenantValidation:
    checks: list[ValidationCheck] = []
    checks.extend(_validate_skill_refs(enabled_skills, default_skill, actor_uid))
    bucket_check = _validate_bucket(documents_bucket)
    if bucket_check is not None:
        checks.append(bucket_check)
    checks.append(_validate_group_tags(derived_group_tags))
    ok = not any(c.level == _LEVEL_ERROR for c in checks)
    return TenantValidation(domain=domain, ok=ok, checks=checks)


@router.post("", response_model=TenantOnboardResponse, status_code=201)
def onboard_tenant(
    body: TenantOnboardRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> TenantOnboardResponse:
    domain = (body.domain or "").strip().lower()
    if not domain or "." not in domain:
        raise HTTPException(
            status_code=422,
            detail="A valid email domain is required (e.g. acmeenergy.com).",
        )

    _require_tenant_admin(user, domain)

    unknown = unknown_skill_refs(body.enabled_skills, body.default_skill, user.uid)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_skill_ref",
                "unknown": unknown,
                "message": f"Unknown skill slug(s): {', '.join(unknown)}",
            },
        )

    existing = get_document(_COLLECTION, domain)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Tenant {domain!r} already exists; edit it via the tenant editor.",
        )

    enabled = body.enabled_skills or None
    derived = body.derived_group_tags or None
    bucket = (body.documents_bucket or "").strip() or None
    data: dict[str, Any] = {
        "display_name": body.display_name.strip(),
        "documents_bucket": bucket,
        "enabled_skills": enabled,
        "derived_group_tags": derived,
        "default_skill": (body.default_skill or "").strip() or None,
    }

    set_document(_COLLECTION, domain, data, merge=False)
    invalidate_client_cache(domain)
    record_admin_action(
        actor_uid=user.uid,
        actor_email=getattr(user, "email", "") or "",
        action="onboard_tenant",
        target=domain,
        before=None,
        after=data,
    )
    log.info("admin.tenants: onboard domain=%s by uid=%s", domain, user.uid)

    validation = build_validation(
        domain=domain,
        enabled_skills=enabled,
        default_skill=data["default_skill"],
        documents_bucket=bucket,
        derived_group_tags=derived,
        actor_uid=user.uid,
    )
    config = ClientConfig(domain=domain, **data)
    return TenantOnboardResponse(domain=domain, config=config, validation=validation)


@router.get("/{domain}/validate", response_model=TenantValidation)
def validate_tenant(
    domain: str,
    user: Annotated[User, Depends(get_current_user)],
) -> TenantValidation:
    domain = domain.strip().lower()
    _require_tenant_admin(user, domain)
    stored = get_client_sync(domain)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Tenant {domain!r} not found")
    return build_validation(
        domain=domain,
        enabled_skills=stored.enabled_skills,
        default_skill=stored.default_skill,
        documents_bucket=stored.documents_bucket,
        derived_group_tags=stored.derived_group_tags,
        actor_uid=user.uid,
    )
