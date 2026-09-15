"""Tool-permission admin plane.

CRUD over the backend-neutral ``tool_permissions`` collection (the second
access plane — tool invocation, enforced by ``auth.permissions``). Runtime
checks and admin mutations therefore use the same DATA_BACKEND in self-hosted
PostgreSQL, Firestore, and memory modes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from admin.audit import record_admin_action
from admin.scope import Scope, domain_of_key
from auth import permissions as perms
from db.persistence import delete_document, get_document, query_documents, set_document

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tool-permissions", tags=["admin-tool-permissions"])

COLLECTION = perms.COLLECTION
_VALID_TYPES = {"user", "domain", "wildcard"}


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
    doc_id: str


def _doc_domain(doc_id: str) -> str:
    return domain_of_key(doc_id)


def _assert_may_touch(scope: Scope, doc_id: str) -> None:
    if (doc_id or "").strip() == "*":
        scope.assert_platform()
        return
    scope.assert_may(_doc_domain(doc_id))


@router.get("", response_model=list[ToolPermissionEntry])
def list_tool_permissions(scope: Scope) -> list[ToolPermissionEntry]:
    out: list[ToolPermissionEntry] = []
    for doc in query_documents(COLLECTION):
        doc_id = doc.pop("__id", "")
        if str(doc_id).strip() == "*":
            if not scope.is_platform:
                continue
        elif not scope.may(_doc_domain(str(doc_id))):
            continue
        try:
            out.append(ToolPermissionEntry(doc_id=doc_id, **doc))
        except Exception as exc:
            log.warning("tool-perms: skipping malformed doc %r (%s)", doc_id, type(exc).__name__)
    log.info("admin.tool_permissions: list by uid=%s count=%d", scope.user.uid, len(out))
    return out


@router.get("/{doc_id:path}", response_model=ToolPermissionEntry)
def get_tool_permission(doc_id: str, scope: Scope) -> ToolPermissionEntry:
    _assert_may_touch(scope, doc_id)
    data = get_document(COLLECTION, doc_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No tool_permissions doc {doc_id!r}")
    return ToolPermissionEntry(doc_id=doc_id, **data)


@router.put("/{doc_id:path}", response_model=ToolPermissionEntry)
def upsert_tool_permission(doc_id: str, body: ToolPermissionDoc, scope: Scope) -> ToolPermissionEntry:
    doc_id = doc_id.strip()
    if not doc_id:
        raise HTTPException(status_code=422, detail="doc id is required")
    _assert_may_touch(scope, doc_id)
    before = get_document(COLLECTION, doc_id)
    data = body.model_dump()
    set_document(COLLECTION, doc_id, data)
    perms.clear_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="upsert_tool_permission",
        target=doc_id,
        before=before,
        after=data,
    )
    log.info("admin.tool_permissions: upsert id=%s by uid=%s", doc_id, scope.user.uid)
    return ToolPermissionEntry(doc_id=doc_id, **data)


@router.delete("/{doc_id:path}", response_model=ToolPermissionEntry)
def delete_tool_permission(doc_id: str, scope: Scope) -> ToolPermissionEntry:
    _assert_may_touch(scope, doc_id)
    before = get_document(COLLECTION, doc_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"No tool_permissions doc {doc_id!r}")
    delete_document(COLLECTION, doc_id)
    perms.clear_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_tenant_id=scope.user.tenant_id or "",
        actor_email=scope.user.email or "",
        action="delete_tool_permission",
        target=doc_id,
        before=before,
        after=None,
    )
    log.info("admin.tool_permissions: delete id=%s by uid=%s", doc_id, scope.user.uid)
    return ToolPermissionEntry(doc_id=doc_id, **before)


__all__ = ["router"]
