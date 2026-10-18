"""Platform-admin account lifecycle for the built-in local JWT provider."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.audit import record_admin_action
from admin.group_tags_routes import is_known_tag
from admin.scope import PlatformScope
from auth import auth_backend
from auth.local_jwt import USER_COLLECTION, _user_doc_id, create_local_user, get_local_user_by_email, hash_password
from db.persistence import get_repository
from db.tenants import TenantDirectory

router = APIRouter(prefix="/accounts", tags=["admin-accounts"])


def _local_only() -> None:
    if auth_backend() != "local-jwt":
        raise HTTPException(409, "Accounts are managed by the configured identity provider")


def account_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": row.get("uid", ""),
        "email": row.get("email", ""),
        "tenantId": row.get("tenantId", ""),
        "disabled": bool(row.get("disabled")),
        "groupTags": row.get("groupTags") or [],
        "createdAt": row.get("createdAt"),
        "updatedAt": row.get("updatedAt"),
    }


def _tenant(tenant_id: str) -> str:
    tenant = TenantDirectory(get_repository()).get(tenant_id.strip())
    if tenant is None or tenant.disabled:
        raise HTTPException(422, "Select an existing, enabled tenant")
    return tenant.tenant_id


class AccountCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)
    tenant_id: str = Field(min_length=1, max_length=200)
    group_tags: list[str] = Field(default_factory=list, max_length=100)


class AccountPatch(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=1, max_length=200)
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


def _audit(scope: PlatformScope, action: str, before: dict | None, after: dict) -> None:
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        tenant_id=str(after.get("tenantId") or ""),
        action=action,
        target=str(after.get("email") or ""),
        before=before,
        after=after,
    )


@router.get("")
def list_accounts(scope: PlatformScope, q: str = "", tenant_id: str = "") -> list[dict[str, Any]]:
    _local_only()
    filters = [("tenantId", "==", tenant_id)] if tenant_id else []
    rows = get_repository().query_documents(USER_COLLECTION, filters=filters, limit=1000)
    query = q.strip().casefold()
    return sorted(
        [account_view(row) for row in rows if not query or query in str(row.get("email") or "").casefold()],
        key=lambda row: row["email"],
    )


@router.post("", status_code=201)
def create_account(body: AccountCreate, scope: PlatformScope) -> dict[str, Any]:
    _local_only()
    tenant_id = _tenant(body.tenant_id)
    if any(not is_known_tag(tag) for tag in body.group_tags):
        raise HTTPException(422, "Unknown group tag")
    if get_local_user_by_email(body.email):
        raise HTTPException(409, "Account already exists")
    try:
        create_local_user(email=body.email, password=body.password, tenant_id=tenant_id, group_tags=body.group_tags)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    view = account_view(get_local_user_by_email(body.email) or {})
    _audit(scope, "create_local_account", None, view)
    return view


@router.patch("/{email}")
def edit_account(email: str, body: AccountPatch, scope: PlatformScope) -> dict[str, Any]:
    _local_only()
    row = get_local_user_by_email(email)
    if row is None:
        raise HTTPException(404, "Account not found")
    before = account_view(row)
    if body.disabled is True and row.get("uid") == scope.user.uid:
        raise HTTPException(422, "You cannot disable your current account")
    updates: dict[str, Any] = {"updatedAt": int(time.time())}
    if body.tenant_id is not None:
        updates["tenantId"] = _tenant(body.tenant_id)
    if body.disabled is not None:
        updates["disabled"] = body.disabled
    updates["tokenVersion"] = int(row.get("tokenVersion", 0)) + 1
    get_repository().update_document(USER_COLLECTION, _user_doc_id(email), updates)
    view = account_view({**row, **updates})
    _audit(scope, "update_local_account", before, view)
    return view


@router.post("/{email}/password")
def reset_password(email: str, body: PasswordReset, scope: PlatformScope) -> dict[str, Any]:
    _local_only()
    row = get_local_user_by_email(email)
    if row is None:
        raise HTTPException(404, "Account not found")
    get_repository().update_document(
        USER_COLLECTION,
        _user_doc_id(email),
        {
            "passwordHash": hash_password(body.password),
            "tokenVersion": int(row.get("tokenVersion", 0)) + 1,
            "updatedAt": int(time.time()),
        },
    )
    view = account_view(row)
    _audit(scope, "reset_local_account_password", view, view)
    return {"email": row["email"], "sessionsRevoked": True}
