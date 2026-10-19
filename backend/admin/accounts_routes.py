"""Platform-admin account lifecycle for the built-in local JWT provider."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from admin.audit import record_admin_action
from admin.scope import Scope
from auth import auth_backend
from auth.capability_access import GROUP_COLLECTION, PermissionGroup
from auth.local_jwt import USER_COLLECTION, _user_doc_id, create_local_user, get_local_user_by_email, hash_password
from db.persistence import get_repository
from db.tenants import TenantDirectory

router = APIRouter(prefix="/accounts", tags=["admin-accounts"])


def _local_only() -> None:
    if auth_backend() != "local-jwt":
        raise HTTPException(409, "Accounts are managed by the configured identity provider")


def _managed_directory() -> None:
    if auth_backend() not in {"local-jwt", "oidc"}:
        raise HTTPException(409, "当前身份源的账号由外部目录维护")


def _groups_for_record(row: dict) -> list[PermissionGroup]:
    result = []
    for group_id in row.get("permissionGroupIds") or []:
        raw = get_repository().get_document(GROUP_COLLECTION, group_id)
        if raw:
            result.append(PermissionGroup.model_validate({k: v for k, v in raw.items() if k != "__id"}))
    return result


def _validate_groups(ids: list[str], tenant_id: str, scope: Scope) -> list[str]:
    for group_id in ids:
        raw = get_repository().get_document(GROUP_COLLECTION, group_id)
        if not raw or raw.get("tenantId") != tenant_id:
            raise HTTPException(422, "只能分配用户所属租户的权限组")
        if raw.get("role") == "tenant-admin":
            scope.assert_platform()
    return sorted(set(ids))


def account_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": row.get("uid", ""),
        "email": row.get("email", ""),
        "tenantId": row.get("tenantId", ""),
        "disabled": bool(row.get("disabled")),
        "permissionGroupIds": row.get("permissionGroupIds") or [],
        "platformAdmin": "aitana-admin" in (row.get("groupTags") or []),
        "createdAt": row.get("createdAt"),
        "updatedAt": row.get("updatedAt"),
    }


def _tenant(tenant_id: str) -> str:
    tenant = TenantDirectory(get_repository()).get(tenant_id.strip())
    if tenant is None or tenant.disabled:
        raise HTTPException(422, "Select an existing, enabled tenant")
    return tenant.tenant_id


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)
    tenant_id: str = Field(min_length=1, max_length=200)
    permission_group_ids: list[str] = Field(default_factory=list, max_length=100)


class AccountPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permission_group_ids: list[str] | None = Field(default=None, max_length=100)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=200)
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


def _audit(scope: Scope, action: str, before: dict | None, after: dict) -> None:
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
def list_accounts(scope: Scope, q: str = "", tenant_id: str = "") -> list[dict[str, Any]]:
    _managed_directory()
    if tenant_id:
        scope.assert_may_tenant(tenant_id)
    filters = [("tenantId", "==", tenant_id)] if tenant_id else []
    rows = get_repository().query_documents(USER_COLLECTION, filters=filters, limit=1000)
    query = q.strip().casefold()
    return sorted(
        [
            account_view(row)
            for row in rows
            if scope.may_tenant(row.get("tenantId")) and (not query or query in str(row.get("email") or "").casefold())
        ],
        key=lambda row: row["email"],
    )


@router.post("", status_code=201)
def create_account(body: AccountCreate, scope: Scope) -> dict[str, Any]:
    _local_only()
    tenant_id = _tenant(body.tenant_id)
    scope.assert_may_tenant(tenant_id)
    groups = _validate_groups(body.permission_group_ids, tenant_id, scope)
    if get_local_user_by_email(body.email):
        raise HTTPException(409, "Account already exists")
    try:
        create_local_user(email=body.email, password=body.password, tenant_id=tenant_id, permission_group_ids=groups)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    view = account_view(get_local_user_by_email(body.email) or {})
    _audit(scope, "create_local_account", None, view)
    return view


@router.patch("/{email}")
def edit_account(email: str, body: AccountPatch, scope: Scope) -> dict[str, Any]:
    _managed_directory()
    row = get_local_user_by_email(email)
    if row is None:
        raise HTTPException(404, "Account not found")
    scope.assert_may_tenant(row.get("tenantId"))
    if "aitana-admin" in (row.get("groupTags") or []):
        raise HTTPException(422, "平台超级管理员为受保护账号")
    if not scope.is_platform and any(group.role == "tenant-admin" for group in _groups_for_record(row)):
        raise HTTPException(403, "租户管理员账号只能由平台管理员调整")
    before = account_view(row)
    if body.disabled is True and _user_doc_id(email) == _user_doc_id(scope.user.email or ""):
        raise HTTPException(422, "You cannot disable your current account")
    updates: dict[str, Any] = {"updatedAt": int(time.time())}
    if body.tenant_id is not None and body.tenant_id.strip() != row.get("tenantId"):
        scope.assert_platform()
        updates["tenantId"] = _tenant(body.tenant_id)
        updates["permissionGroupIds"] = []
    if body.permission_group_ids is not None:
        updates["permissionGroupIds"] = _validate_groups(
            body.permission_group_ids,
            updates.get("tenantId", row["tenantId"]),
            scope,
        )
    if body.disabled is not None and body.disabled != bool(row.get("disabled")):
        updates["disabled"] = body.disabled
    if "tenantId" in updates or "disabled" in updates:
        updates["tokenVersion"] = int(row.get("tokenVersion", 0)) + 1
    get_repository().update_document(USER_COLLECTION, _user_doc_id(email), updates)
    view = account_view({**row, **updates})
    _audit(scope, "update_local_account", before, view)
    return view


@router.post("/{email}/password")
def reset_password(email: str, body: PasswordReset, scope: Scope) -> dict[str, Any]:
    _local_only()
    row = get_local_user_by_email(email)
    if row is None:
        raise HTTPException(404, "Account not found")
    scope.assert_may_tenant(row.get("tenantId"))
    if "aitana-admin" in (row.get("groupTags") or []):
        scope.assert_platform()
    if any(group.role == "tenant-admin" for group in _groups_for_record(row)):
        scope.assert_platform()
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
