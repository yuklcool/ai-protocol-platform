"""Tool-permission admin plane.

CRUD over the backend-neutral ``tool_permissions`` collection (the second
access plane — tool invocation, enforced by ``auth.permissions``). Runtime
checks and admin mutations therefore use the same DATA_BACKEND in self-hosted
PostgreSQL, Firestore, and memory modes.

First-class tenant permission documents use ``tenant:<tenant_id>``. Legacy
email/domain keys remain readable during migration, but tenant-admin scope is
resolved only from trusted ownership sources: an explicit stored ``tenantId``,
a first-class tenant key, an exact local-auth user record, or the authoritative
``tenant_domains`` mapping. Email syntax alone is never treated as ownership.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from admin.audit import record_admin_action
from admin.scope import Scope, domain_of_key
from auth import permissions as perms
from auth.local_jwt import get_local_user_by_email
from db.persistence import delete_document, get_document, query_documents, set_document
from db.tenants import tenant_id_for_domain

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tool-permissions", tags=["admin-tool-permissions"])

COLLECTION = perms.COLLECTION
_VALID_TYPES = {"user", "domain", "tenant", "wildcard"}


class ToolPermissionDoc(BaseModel):
    type: str
    tools: list[str] = []
    denied: list[str] = []

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(_VALID_TYPES)}")
        return v


class ToolPermissionEntry(ToolPermissionDoc):
    model_config = ConfigDict(populate_by_name=True)

    doc_id: str
    tenant_id: str | None = Field(default=None, alias="tenantId")


def _tenant_from_local_user(email: str) -> str:
    """Return only an explicitly persisted local-user tenant assignment."""
    if not email or "@" not in email:
        return ""
    try:
        record = get_local_user_by_email(email)
    except Exception as exc:
        log.debug("tool-perms: local user ownership lookup failed for %s: %s", email, exc)
        return ""
    if not record:
        return ""
    return str(record.get("tenantId") or "").strip()


def _trusted_tenant_owner(doc_id: str, data: dict | None = None) -> str:
    """Resolve permission ownership without guessing from an email address."""
    key = (doc_id or "").strip()
    if not key or key == "*":
        return ""

    if key.startswith(perms.TENANT_PREFIX):
        return key[len(perms.TENANT_PREFIX) :].strip()

    stored = str((data or {}).get("tenantId") or "").strip()
    if stored:
        return stored

    doc_type = str((data or {}).get("type") or "").strip()
    if doc_type == "user" or "@" in key:
        return _tenant_from_local_user(key)

    domain = domain_of_key(key)
    if not domain and doc_type == "domain":
        domain = key.casefold().rstrip(".")
    if not domain:
        return ""
    return str(tenant_id_for_domain(domain) or "").strip()


def _assert_shape(doc_id: str, body: ToolPermissionDoc) -> None:
    key = (doc_id or "").strip()
    if key == "*" and body.type != "wildcard":
        raise HTTPException(status_code=422, detail="'*' permission must use type='wildcard'")
    if key != "*" and body.type == "wildcard":
        raise HTTPException(status_code=422, detail="wildcard permission must use doc id '*'")
    is_tenant_key = key.startswith(perms.TENANT_PREFIX)
    if is_tenant_key and not key[len(perms.TENANT_PREFIX) :].strip():
        raise HTTPException(status_code=422, detail="tenant permission requires a non-empty tenant id")
    if is_tenant_key and body.type != "tenant":
        raise HTTPException(status_code=422, detail="tenant:<tenant_id> permission must use type='tenant'")
    if body.type == "tenant" and not is_tenant_key:
        raise HTTPException(status_code=422, detail="type='tenant' requires doc id tenant:<tenant_id>")


def _assert_may_touch(scope: Scope, doc_id: str, data: dict | None = None) -> str:
    if (doc_id or "").strip() == "*":
        scope.assert_platform()
        return ""
    if scope.is_platform:
        return _trusted_tenant_owner(doc_id, data)
    tenant_id = _trusted_tenant_owner(doc_id, data)
    if not tenant_id:
        # Unowned legacy records stay platform-only until an explicit migration
        # establishes first-class ownership.
        raise HTTPException(status_code=403, detail="Permission has no trusted tenant ownership")
    scope.assert_may_tenant(tenant_id)
    return tenant_id


def _entry(doc_id: str, data: dict) -> ToolPermissionEntry:
    payload = dict(data)
    owner = _trusted_tenant_owner(doc_id, payload)
    if owner:
        payload["tenantId"] = owner
    return ToolPermissionEntry(doc_id=doc_id, **payload)


@router.get("", response_model=list[ToolPermissionEntry])
def list_tool_permissions(scope: Scope) -> list[ToolPermissionEntry]:
    out: list[ToolPermissionEntry] = []
    for raw in query_documents(COLLECTION):
        doc = dict(raw)
        doc_id = str(doc.pop("__id", ""))
        try:
            if doc_id == "*":
                if not scope.is_platform:
                    continue
            elif not scope.is_platform:
                tenant_id = _trusted_tenant_owner(doc_id, doc)
                if not tenant_id or not scope.may_tenant(tenant_id):
                    continue
            out.append(_entry(doc_id, doc))
        except Exception as exc:
            log.warning("tool-perms: skipping malformed doc %r (%s)", doc_id, type(exc).__name__)
    log.info("admin.tool_permissions: list by uid=%s count=%d", scope.user.uid, len(out))
    return out


@router.get("/{doc_id:path}", response_model=ToolPermissionEntry)
def get_tool_permission(doc_id: str, scope: Scope) -> ToolPermissionEntry:
    data = get_document(COLLECTION, doc_id)
    if data is None:
        # For tenant admins, do not use the requested email syntax to infer
        # ownership merely to turn this into a 404.
        _assert_may_touch(scope, doc_id)
        raise HTTPException(status_code=404, detail=f"No tool_permissions doc {doc_id!r}")
    _assert_may_touch(scope, doc_id, data)
    return _entry(doc_id, data)


@router.put("/{doc_id:path}", response_model=ToolPermissionEntry)
def upsert_tool_permission(doc_id: str, body: ToolPermissionDoc, scope: Scope) -> ToolPermissionEntry:
    doc_id = doc_id.strip()
    if not doc_id:
        raise HTTPException(status_code=422, detail="doc id is required")
    _assert_shape(doc_id, body)
    before = get_document(COLLECTION, doc_id)
    owner = _assert_may_touch(scope, doc_id, before or body.model_dump())
    data = body.model_dump()
    # Derive ownership from trusted sources/key. Never accept a request body
    # tenant id as an authorization input.
    trusted_owner = owner or _trusted_tenant_owner(doc_id, data)
    if trusted_owner:
        data["tenantId"] = trusted_owner
    set_document(COLLECTION, doc_id, data)
    perms.clear_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="upsert_tool_permission",
        target=doc_id,
        tenant_id=trusted_owner or "",
        before=before,
        after=data,
    )
    log.info("admin.tool_permissions: upsert id=%s tenant=%s by uid=%s", doc_id, trusted_owner, scope.user.uid)
    return _entry(doc_id, data)


@router.delete("/{doc_id:path}", response_model=ToolPermissionEntry)
def delete_tool_permission(doc_id: str, scope: Scope) -> ToolPermissionEntry:
    before = get_document(COLLECTION, doc_id)
    if before is None:
        _assert_may_touch(scope, doc_id)
        raise HTTPException(status_code=404, detail=f"No tool_permissions doc {doc_id!r}")
    owner = _assert_may_touch(scope, doc_id, before)
    delete_document(COLLECTION, doc_id)
    perms.clear_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="delete_tool_permission",
        target=doc_id,
        tenant_id=owner or "",
        before=before,
        after=None,
    )
    log.info("admin.tool_permissions: delete id=%s tenant=%s by uid=%s", doc_id, owner, scope.user.uid)
    return _entry(doc_id, before)


__all__ = ["router"]
