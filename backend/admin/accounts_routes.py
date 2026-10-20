"""Administrator account lifecycle and per-user personal profiles."""

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from admin.audit import record_admin_action
from admin.scope import Scope
from auth import auth_backend
from auth.local_jwt import USER_COLLECTION, _user_doc_id, create_local_user, get_local_user_by_email, hash_password
from db.persistence import get_repository
from db.user_profiles import UserProfile, get_user_profile, save_user_profile

router = APIRouter(prefix="/accounts", tags=["admin-accounts"])


def _managed_directory() -> None:
    if auth_backend() not in {"local-jwt", "oidc"}:
        raise HTTPException(409, "Accounts are managed by the configured identity provider")


def _local_only() -> None:
    if auth_backend() != "local-jwt":
        raise HTTPException(409, "Password accounts require the built-in identity provider")


def account_view(row: dict) -> dict:
    return {
        "uid": row.get("uid", ""),
        "email": row.get("email", ""),
        "disabled": bool(row.get("disabled")),
        "platformAdmin": "aitana-admin" in (row.get("groupTags") or []),
        "createdAt": row.get("createdAt"),
        "updatedAt": row.get("updatedAt"),
    }


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class AccountPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


def _account(email: str) -> dict:
    _managed_directory()
    row = get_local_user_by_email(email)
    if row is None:
        raise HTTPException(404, "Account not found")
    return row


def _audit(scope: Scope, action: str, before: dict | None, after: dict) -> None:
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email,
        action=action,
        target=str(after.get("email") or ""),
        before=before,
        after=after,
    )


@router.get("")
def list_accounts(scope: Scope, q: str = "") -> list[dict]:
    _managed_directory()
    rows = get_repository().query_documents(USER_COLLECTION, limit=1000)
    return sorted(
        [account_view(row) for row in rows if q.strip().casefold() in str(row.get("email") or "").casefold()],
        key=lambda row: row["email"],
    )


@router.post("", status_code=201)
def create_account(body: AccountCreate, scope: Scope) -> dict:
    _local_only()
    if get_local_user_by_email(body.email):
        raise HTTPException(409, "Account already exists")
    try:
        create_local_user(email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    view = account_view(_account(body.email))
    _audit(scope, "create_local_account", None, view)
    return view


@router.patch("/{email}")
def edit_account(email: str, body: AccountPatch, scope: Scope) -> dict:
    row = _account(email)
    if body.disabled and (row.get("uid") == scope.user.uid or "aitana-admin" in (row.get("groupTags") or [])):
        raise HTTPException(422, "The current account and platform administrator cannot be disabled")
    updates = {"updatedAt": int(time.time())}
    if body.disabled is not None and body.disabled != bool(row.get("disabled")):
        updates.update(disabled=body.disabled, tokenVersion=int(row.get("tokenVersion", 0)) + 1)
    get_repository().update_document(USER_COLLECTION, _user_doc_id(email), updates)
    view = account_view({**row, **updates})
    _audit(scope, "update_local_account", account_view(row), view)
    return view


@router.get("/{email}/profile")
def account_profile(email: str, scope: Scope) -> UserProfile:
    return get_user_profile(_account(email)["uid"])


@router.put("/{email}/profile")
def edit_account_profile(email: str, body: UserProfile, scope: Scope) -> UserProfile:
    row = _account(email)
    result = save_user_profile(row["uid"], body)
    _audit(scope, "update_user_profile", None, account_view(row))
    return result


@router.post("/{email}/password")
def reset_password(email: str, body: PasswordReset, scope: Scope) -> dict:
    _local_only()
    row = _account(email)
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


@router.get("/{email}/skills")
def account_skills(email: str, scope: Scope) -> list[dict]:
    from skills.skill_config import list_skills

    uid = _account(email)["uid"]
    return [
        {"skillId": skill.skill_id, "displayName": skill.display_name, "name": skill.name}
        for skill in list_skills(owner_id=uid, limit=200)
        if skill.owner_id == uid
    ]
