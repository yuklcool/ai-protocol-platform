"""Admin routes for client/tenant management.

Manages ``clients/{domain}`` records through the backend-neutral persistence
facade. The same admin API therefore reads/writes the active DATA_BACKEND
(memory, Firestore, or PostgreSQL) instead of splitting runtime reads and admin
writes across different stores.

v6.16.0: scope-aware. A platform admin sees and edits every tenant; a
``tenant-admin:{domain}`` holder sees and edits only its own. The list endpoint
FILTERS rather than 403s — a tenant admin listing tenants should get their own,
not an error.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import Scope
from admin.tenants import unknown_skill_refs
from auth import User, get_current_user
from db.clients import ClientConfig, invalidate_client_cache
from db.persistence import delete_document, get_document, query_documents, set_document

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/clients", tags=["admin-clients"])
_COLLECTION = "clients"

# ---------------------------------------------------------------------------
# Non-admin: the caller's own resolved client config
# ---------------------------------------------------------------------------

me_router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientMeResponse(BaseModel):
    domain: str
    display_name: str = ""
    enabled_skills: list[str] | None = None
    default_skill: str | None = None


@me_router.get("/me", response_model=ClientMeResponse)
def get_my_client(user: Annotated[User, Depends(get_current_user)]) -> ClientMeResponse:
    from db.clients import _user_domain, get_client_cached, resolve_default_skill

    domain = _user_domain(user)
    client = get_client_cached(domain) if domain else None
    return ClientMeResponse(
        domain=domain,
        display_name=client.display_name if client else "",
        enabled_skills=client.enabled_skills if client else None,
        default_skill=resolve_default_skill(user),
    )


class ClientConfigUpdate(BaseModel):
    documents_bucket: str | None = None
    display_name: str = ""
    enabled_skills: list[str] | None = None
    derived_group_tags: list[str] | None = None
    default_skill: str | None = None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ClientConfig])
def list_clients(scope: Scope) -> list[ClientConfig]:
    docs = query_documents(_COLLECTION)
    configs = []
    for doc in docs:
        domain = doc.pop("__id", "")
        doc.pop("domain", None)
        if not scope.may(domain):
            continue
        configs.append(ClientConfig(domain=domain, **doc))
    log.info(
        "admin.clients: list by uid=%s scope=%s count=%d",
        scope.user.uid,
        "platform" if scope.is_platform else "tenant",
        len(configs),
    )
    return configs


# ---------------------------------------------------------------------------
# Get one
# ---------------------------------------------------------------------------


@router.get("/{domain}", response_model=ClientConfig)
def get_client(domain: str, scope: Scope) -> ClientConfig:
    scope.assert_may(domain)
    data = get_document(_COLLECTION, domain)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Client {domain!r} not found")
    data.pop("domain", None)
    return ClientConfig(domain=domain, **data)


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


@router.put("/{domain}", response_model=ClientConfig)
def upsert_client(
    domain: str,
    body: ClientConfigUpdate,
    scope: Scope,
) -> ClientConfig:
    scope.assert_may(domain)
    data = body.model_dump(exclude_unset=True)
    if data.get("enabled_skills") == []:
        data["enabled_skills"] = None
    if data.get("derived_group_tags") == []:
        data["derived_group_tags"] = None

    unknown = unknown_skill_refs(
        data.get("enabled_skills") if "enabled_skills" in data else None,
        data.get("default_skill") if "default_skill" in data else None,
        scope.user.uid,
    )
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_skill_ref",
                "unknown": unknown,
                "message": f"Unknown skill slug(s): {', '.join(unknown)}",
            },
        )

    before = get_document(_COLLECTION, domain)
    set_document(_COLLECTION, domain, data, merge=True)
    invalidate_client_cache(domain)

    merged = get_document(_COLLECTION, domain) or data
    merged.pop("domain", None)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        action="upsert_client",
        target=domain,
        before=before,
        after=merged,
    )
    log.info(
        "admin.clients: upsert domain=%s by uid=%s enabled_skills_count=%s derived_tags_count=%s",
        domain,
        scope.user.uid,
        len(data.get("enabled_skills") or []),
        len(data.get("derived_group_tags") or []),
    )
    return ClientConfig(domain=domain, **merged)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{domain}", response_model=ClientConfig)
def delete_client(domain: str, scope: Scope) -> ClientConfig:
    scope.assert_may(domain)
    data = get_document(_COLLECTION, domain)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Client {domain!r} not found")
    delete_document(_COLLECTION, domain)
    invalidate_client_cache(domain)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        action="delete_client",
        target=domain,
        before=data,
        after=None,
    )
    log.info("admin.clients: delete domain=%s by uid=%s", domain, scope.user.uid)
    data.pop("domain", None)
    return ClientConfig(domain=domain, **data)
