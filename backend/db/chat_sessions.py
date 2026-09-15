"""Backend-neutral repository helpers for ChatSessionIndex.

Chat-session metadata follows ``DATA_BACKEND`` and carries an explicit stable
``tenantId``. Tenant isolation is enforced independently of ordinary sharing
ACLs: a public/tagged/domain session is still invisible outside its tenant.

Legacy rows without ``tenantId`` are not trusted merely because their
``ownerDomain`` resembles the caller. The domain must resolve through the
first-class tenant directory; an unmapped legacy row is therefore fail-closed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from auth.access_context import AccessContext, can_access
from db.models.access import AccessControl
from db.models.chat_session import ChatSessionIndex
from db.persistence import (
    array_union_field,
    get_document,
    query_documents,
    set_document,
    update_document,
)
from db.tenants import normalize_tenant_id, tenant_id_for_domain

logger = logging.getLogger(__name__)

_COLLECTION = "chat_sessions"


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Tenant boundary
# ---------------------------------------------------------------------------


def resolved_session_tenant_id(idx: ChatSessionIndex) -> str:
    """Return a row's stable tenant id, resolving legacy domain rows safely.

    New rows always carry ``tenantId``. Historical rows may only cross the
    migration bridge when ``ownerDomain`` is registered in ``tenant_domains``
    (or has a legacy clients record). Unknown domains resolve to an empty string
    and are denied by every tenant-aware reader.
    """
    explicit = normalize_tenant_id(idx.tenant_id)
    if explicit:
        return explicit
    if not idx.owner_domain:
        return ""
    return normalize_tenant_id(tenant_id_for_domain(idx.owner_domain) or "")


def session_in_tenant(idx: ChatSessionIndex, tenant_id: str) -> bool:
    expected = normalize_tenant_id(tenant_id)
    if not expected:
        return False
    return resolved_session_tenant_id(idx) == expected


def session_tenant_allowed(idx: ChatSessionIndex, viewer_ctx: AccessContext) -> bool:
    """Hard tenant boundary used before any ordinary session ACL evaluation."""
    return session_in_tenant(idx, viewer_ctx.tenant_id)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def owner_domain_of(email: str | None) -> str:
    """Email -> lower-cased domain retained only as a migration/access hint."""
    email = (email or "").strip().lower()
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def create_session_index(
    *,
    session_id: str,
    skill_id: str,
    owner_uid: str,
    tenant_id: str,
    access_control: AccessControl,
    document_ids: list[str] | None = None,
    first_message_at: datetime | None = None,
    owner_domain: str = "",
    provisional: bool = False,
) -> ChatSessionIndex:
    """Persist a new tenant-scoped ChatSessionIndex row.

    New writes fail closed when the authenticated identity has no stable tenant
    scope. This prevents creating unattributable rows that later become visible
    through owner/domain ACL shortcuts.
    """
    stable_tenant_id = normalize_tenant_id(tenant_id)
    if not stable_tenant_id:
        raise ValueError("tenant_id is required for new chat sessions")

    now = first_message_at or _utcnow()
    idx = ChatSessionIndex(
        sessionId=session_id,
        tenantId=stable_tenant_id,
        documentIds=list(document_ids) if document_ids else [],
        skillId=skill_id,
        ownerUid=owner_uid,
        ownerDomain=(owner_domain or "").strip().lower(),
        accessControl=access_control,
        firstMessageAt=now,
        lastMessageAt=now,
        provisional=provisional,
    )
    set_document(_COLLECTION, session_id, _to_document(idx))
    return idx


def clear_provisional(session_id: str, not_after: datetime | None = None) -> None:
    stamp = _utcnow()
    if not_after is not None and not_after < stamp:
        stamp = not_after
    update_document(
        _COLLECTION,
        session_id,
        {"provisional": False, "firstMessageAt": stamp.isoformat()},
    )


def save_session_index(idx: ChatSessionIndex) -> None:
    set_document(_COLLECTION, idx.session_id, _to_document(idx))


def update_session_fields(session_id: str, fields: dict) -> None:
    update_document(_COLLECTION, session_id, fields)


def set_session_skill(session_id: str, new_skill_id: str, prev_skill_id: str | None = None) -> None:
    history = [skill for skill in (prev_skill_id, new_skill_id) if skill]
    if history:
        array_union_field(_COLLECTION, session_id, "skillHistory", history)
    update_document(_COLLECTION, session_id, {"skillId": new_skill_id})


def add_session_documents(session_id: str, doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    array_union_field(_COLLECTION, session_id, "documentIds", list(doc_ids))


def soft_delete_session(session_id: str) -> None:
    update_document(_COLLECTION, session_id, {"archivedAt": _utcnow().isoformat()})


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_session_index(session_id: str) -> ChatSessionIndex | None:
    """Raw internal read.

    Request handlers MUST pair this with :func:`session_tenant_allowed` (or use
    a tenant-aware wrapper) before applying sharing ACLs. Internal mutation
    helpers keep this raw form for migration/reconciliation jobs.
    """
    data = get_document(_COLLECTION, session_id)
    if data is None:
        return None
    return _from_document(data, session_id)


def get_session_index_for_tenant(session_id: str, tenant_id: str) -> ChatSessionIndex | None:
    idx = get_session_index(session_id)
    if idx is None or not session_in_tenant(idx, tenant_id):
        return None
    return idx


SessionFilter = Literal["mine", "team", "all"]


def _hydrate_rows(rows: list[dict]) -> list[tuple[str, ChatSessionIndex]]:
    hydrated: list[tuple[str, ChatSessionIndex]] = []
    for raw in rows:
        data = dict(raw)
        doc_id = str(data.pop("__id", ""))
        if not doc_id:
            continue
        try:
            hydrated.append((doc_id, _from_document(data, doc_id)))
        except Exception as exc:
            logger.warning("malformed chat_sessions/%s: %s", doc_id, exc)
    return hydrated


def list_sessions_for_document(
    doc_id: str,
    viewer_ctx: AccessContext,
    filter: SessionFilter = "all",
    page_size: int = 20,
    cursor: str | None = None,
) -> tuple[list[ChatSessionIndex], str | None]:
    """List visible, same-tenant, non-archived sessions for one document."""
    rows = query_documents(
        _COLLECTION,
        filters=[
            ("documentIds", "array_contains", doc_id),
            ("archivedAt", "==", None),
        ],
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        start_after_id=cursor,
        # Tenant filtering may discard rows after the backend query, including
        # legacy rows, so over-fetch just as ACL filtering already does.
        limit=page_size * 4,
    )

    results: list[ChatSessionIndex] = []
    last_id: str | None = None
    for row_id, idx in _hydrate_rows(rows):
        if not session_tenant_allowed(idx, viewer_ctx):
            continue
        if not can_access(idx.access_control, viewer_ctx, idx.owner_uid):
            continue
        if filter == "mine" and idx.owner_uid != viewer_ctx.uid:
            continue
        if filter == "team" and idx.owner_uid == viewer_ctx.uid:
            continue
        if idx.provisional:
            last_id = row_id
            continue
        results.append(idx)
        last_id = row_id
        if len(results) >= page_size:
            break

    next_cursor = last_id if len(results) == page_size else None
    return results, next_cursor


def list_sessions_for_skill(
    skill_id: str | None,
    owner_uid: str,
    *,
    tenant_id: str,
    page_size: int = 20,
    cursor: str | None = None,
) -> tuple[list[ChatSessionIndex], str | None]:
    """List one user's same-tenant, non-archived sessions, newest first."""
    filters: list[tuple[str, str, object]] = [
        ("ownerUid", "==", owner_uid),
        ("archivedAt", "==", None),
    ]
    if skill_id is not None:
        filters.insert(0, ("skillId", "==", skill_id))

    rows = query_documents(
        _COLLECTION,
        filters=filters,
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        start_after_id=cursor,
        # Same uid can legitimately exist in several tenants (OIDC federation,
        # service identities), so filter after hydration for legacy support.
        limit=(page_size * 4) + 1,
    )

    results: list[ChatSessionIndex] = []
    last_id: str | None = None
    for row_id, idx in _hydrate_rows(rows):
        if not session_in_tenant(idx, tenant_id):
            continue
        if idx.provisional:
            last_id = row_id
            continue
        results.append(idx)
        last_id = row_id
        if len(results) >= page_size:
            break

    next_cursor = last_id if len(results) == page_size else None
    return results, next_cursor


def most_recent_session_for_user(
    owner_uid: str,
    *,
    tenant_id: str,
    limit: int = 10,
) -> list[ChatSessionIndex]:
    """Return a user's most-recent same-tenant, non-archived sessions."""
    rows = query_documents(
        _COLLECTION,
        filters=[("ownerUid", "==", owner_uid), ("archivedAt", "==", None)],
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        limit=max(limit * 4, limit),
    )
    out: list[ChatSessionIndex] = []
    for _, idx in _hydrate_rows(rows):
        if not session_in_tenant(idx, tenant_id):
            continue
        if idx.provisional:
            continue
        out.append(idx)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_document(idx: ChatSessionIndex) -> dict:
    data = idx.model_dump(by_alias=True, exclude_none=False)
    for key in ("firstMessageAt", "lastMessageAt", "archivedAt"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    if "accessControl" in data and hasattr(data["accessControl"], "model_dump"):
        data["accessControl"] = data["accessControl"].model_dump(exclude_none=True)
    return data


def _from_document(data: dict, doc_id: str) -> ChatSessionIndex:
    clean = {key: value for key, value in data.items() if key != "__id"}
    if "sessionId" not in clean:
        clean = {**clean, "sessionId": doc_id}
    return ChatSessionIndex.model_validate(clean)


_to_firestore = _to_document
_from_firestore = _from_document


__all__ = [
    "SessionFilter",
    "add_session_documents",
    "clear_provisional",
    "create_session_index",
    "get_session_index",
    "get_session_index_for_tenant",
    "list_sessions_for_document",
    "list_sessions_for_skill",
    "most_recent_session_for_user",
    "owner_domain_of",
    "resolved_session_tenant_id",
    "save_session_index",
    "session_in_tenant",
    "session_tenant_allowed",
    "set_session_skill",
    "soft_delete_session",
    "update_session_fields",
]
