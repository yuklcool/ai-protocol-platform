"""User-owned chat indexes with explicit sharing ACLs."""

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
from observability.user_context import get_resource_user_id

logger = logging.getLogger(__name__)

_COLLECTION = "chat_sessions"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _assert_mutation_scope(session_id: str) -> ChatSessionIndex | None:
    idx = get_session_index(session_id)
    if idx is not None and idx.owner_uid != get_resource_user_id():
        raise PermissionError("Session belongs to another user")
    return idx


def owner_domain_of(email: str | None) -> str:
    email = (email or "").strip().lower()
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def create_session_index(
    *,
    session_id: str,
    skill_id: str,
    owner_uid: str,
    access_control: AccessControl,
    agent_id: str = "aitana_platform",
    app_name: str = "aitana_platform",
    document_ids: list[str] | None = None,
    first_message_at: datetime | None = None,
    owner_domain: str = "",
    provisional: bool = False,
) -> ChatSessionIndex:
    """Persist an authenticated user-owned chat index."""
    if not owner_uid or owner_uid != get_resource_user_id():
        raise PermissionError("Authenticated session owner required")

    existing = get_session_index(session_id)
    if existing is not None and existing.owner_uid != owner_uid:
        raise PermissionError("refusing to overwrite a chat session from another user")

    now = first_message_at or _utcnow()
    idx = ChatSessionIndex(
        sessionId=session_id,
        documentIds=list(document_ids) if document_ids else [],
        documentTabs=[{"id": ref, "included": True} for ref in (document_ids or [])],
        agentId=agent_id,
        appName=app_name,
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
    _assert_mutation_scope(session_id)
    stamp = _utcnow()
    if not_after is not None and not_after < stamp:
        stamp = not_after
    update_document(_COLLECTION, session_id, {"provisional": False, "firstMessageAt": stamp.isoformat()})


def update_session_fields(session_id: str, fields: dict) -> None:
    _assert_mutation_scope(session_id)
    update_document(_COLLECTION, session_id, fields)


def set_session_skill(session_id: str, new_skill_id: str, prev_skill_id: str | None = None) -> None:
    _assert_mutation_scope(session_id)
    history = [skill for skill in (prev_skill_id, new_skill_id) if skill]
    if history:
        array_union_field(_COLLECTION, session_id, "skillHistory", history)
    update_document(_COLLECTION, session_id, {"skillId": new_skill_id})


def set_session_documents(session_id: str, doc_ids: list[str]) -> None:
    """每轮选择替换,保留仍打开但不参与分析的文件标签。"""
    _assert_mutation_scope(session_id)
    idx = get_session_index(session_id)
    if idx is None:
        raise ValueError("Session not found")
    selected = set(doc_ids)
    order = list(dict.fromkeys([str(tab["id"]) for tab in idx.document_tabs] + doc_ids))
    update_session_fields(
        session_id,
        {
            "documentIds": list(doc_ids),
            "documentTabs": [{"id": ref, "included": ref in selected} for ref in order],
        },
    )


def soft_delete_session(session_id: str) -> None:
    _assert_mutation_scope(session_id)
    update_document(_COLLECTION, session_id, {"archivedAt": _utcnow().isoformat()})


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_session_index(session_id: str) -> ChatSessionIndex | None:
    """Raw internal read. Request handlers must still apply AccessContext ACLs."""
    data = get_document(_COLLECTION, session_id)
    if data is None:
        return None
    return _from_document(data, session_id)


def app_name_for_session(idx: ChatSessionIndex) -> str:
    """Return the ADK app namespace for a metadata row."""
    return idx.app_name or "aitana_platform"


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
    rows = query_documents(
        _COLLECTION,
        filters=[("documentIds", "array_contains", doc_id), ("archivedAt", "==", None)],
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        start_after_id=cursor,
        limit=page_size * 4,
    )

    results: list[ChatSessionIndex] = []
    last_id: str | None = None
    for row_id, idx in _hydrate_rows(rows):
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

    return results, (last_id if len(results) == page_size else None)


def list_sessions_for_skill(
    skill_id: str | None,
    owner_uid: str,
    *,
    page_size: int = 20,
    cursor: str | None = None,
) -> tuple[list[ChatSessionIndex], str | None]:
    """List one user's non-archived sessions, newest first."""
    if owner_uid != get_resource_user_id():
        raise PermissionError("Session belongs to another user")
    filters: list[tuple[str, str, object]] = [("ownerUid", "==", owner_uid), ("archivedAt", "==", None)]
    if skill_id is not None:
        filters.insert(0, ("skillId", "==", skill_id))

    rows = query_documents(
        _COLLECTION,
        filters=filters,
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        start_after_id=cursor,
        limit=(page_size * 4) + 1,
    )

    results: list[ChatSessionIndex] = []
    last_id: str | None = None
    for row_id, idx in _hydrate_rows(rows):
        if idx.provisional:
            last_id = row_id
            continue
        results.append(idx)
        last_id = row_id
        if len(results) >= page_size:
            break

    return results, (last_id if len(results) == page_size else None)


def most_recent_session_for_user(
    owner_uid: str,
    *,
    limit: int = 10,
) -> list[ChatSessionIndex]:
    if owner_uid != get_resource_user_id():
        raise PermissionError("Session belongs to another user")
    rows = query_documents(
        _COLLECTION,
        filters=[("ownerUid", "==", owner_uid), ("archivedAt", "==", None)],
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        limit=max(limit * 4, limit),
    )
    out: list[ChatSessionIndex] = []
    for _, idx in _hydrate_rows(rows):
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
    "app_name_for_session",
    "clear_provisional",
    "create_session_index",
    "get_session_index",
    "list_sessions_for_document",
    "list_sessions_for_skill",
    "most_recent_session_for_user",
    "owner_domain_of",
    "set_session_skill",
    "soft_delete_session",
    "update_session_fields",
]
