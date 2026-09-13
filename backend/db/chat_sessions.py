"""Backend-neutral repository helpers for ChatSessionIndex.

Chat-session metadata now follows ``DATA_BACKEND`` instead of calling the
Firestore SDK directly. Query/filter/order/cursor behavior is expressed through
``db.persistence`` and concurrency-sensitive list updates use the repository's
atomic array-union operation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from auth.access_context import AccessContext, can_access
from db.persistence import (
    array_union_field,
    get_document,
    query_documents,
    set_document,
    update_document,
)
from db.models.access import AccessControl
from db.models.chat_session import ChatSessionIndex

logger = logging.getLogger(__name__)

_COLLECTION = "chat_sessions"


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def owner_domain_of(email: str | None) -> str:
    """Email -> lower-cased domain for the ``ownerDomain`` index field."""
    email = (email or "").strip().lower()
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def create_session_index(
    *,
    session_id: str,
    skill_id: str,
    owner_uid: str,
    access_control: AccessControl,
    document_ids: list[str] | None = None,
    first_message_at: datetime | None = None,
    owner_domain: str = "",
    provisional: bool = False,
) -> ChatSessionIndex:
    """Persist a new ChatSessionIndex row. Idempotent: overwrites if exists."""
    now = first_message_at or _utcnow()
    idx = ChatSessionIndex(
        sessionId=session_id,
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
    """Promote a bootstrap-provisional row to a real session.

    ``not_after`` prevents ``firstMessageAt`` from being stamped later than the
    turn's already-recorded ``lastMessageAt``.
    """
    stamp = _utcnow()
    if not_after is not None and not_after < stamp:
        stamp = not_after
    update_document(
        _COLLECTION,
        session_id,
        {"provisional": False, "firstMessageAt": stamp.isoformat()},
    )


def save_session_index(idx: ChatSessionIndex) -> None:
    """Overwrite the full index row (used after counters/title changes)."""
    set_document(_COLLECTION, idx.session_id, _to_document(idx))


def update_session_fields(session_id: str, fields: dict) -> None:
    """Partial update of session-index fields."""
    update_document(_COLLECTION, session_id, fields)


def set_session_skill(session_id: str, new_skill_id: str, prev_skill_id: str | None = None) -> None:
    """Point the session at its current skill and retain unique skill history."""
    history = [skill for skill in (prev_skill_id, new_skill_id) if skill]
    if history:
        array_union_field(_COLLECTION, session_id, "skillHistory", history)
    update_document(_COLLECTION, session_id, {"skillId": new_skill_id})


def add_session_documents(session_id: str, doc_ids: list[str]) -> None:
    """Atomically add document IDs without clobbering concurrent turns."""
    if not doc_ids:
        return
    array_union_field(_COLLECTION, session_id, "documentIds", list(doc_ids))


def soft_delete_session(session_id: str) -> None:
    """Soft-delete: set archivedAt to now. Owner-only gate is in the route."""
    update_document(_COLLECTION, session_id, {"archivedAt": _utcnow().isoformat()})


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_session_index(session_id: str) -> ChatSessionIndex | None:
    data = get_document(_COLLECTION, session_id)
    if data is None:
        return None
    return _from_document(data, session_id)


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
    """List visible, non-archived sessions associated with one document."""
    rows = query_documents(
        _COLLECTION,
        filters=[
            ("documentIds", "array_contains", doc_id),
            ("archivedAt", "==", None),
        ],
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
        if getattr(idx, "provisional", False):
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
    page_size: int = 20,
    cursor: str | None = None,
) -> tuple[list[ChatSessionIndex], str | None]:
    """List one user's non-archived sessions, newest first."""
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
        limit=page_size + 1,
    )

    results: list[ChatSessionIndex] = []
    last_id: str | None = None
    for row_id, idx in _hydrate_rows(rows):
        if getattr(idx, "provisional", False):
            last_id = row_id
            continue
        results.append(idx)
        last_id = row_id
        if len(results) >= page_size:
            break

    next_cursor = last_id if len(results) == page_size else None
    return results, next_cursor


def most_recent_session_for_user(owner_uid: str, limit: int = 10) -> list[ChatSessionIndex]:
    """Return a user's most-recent non-archived sessions across all skills."""
    rows = query_documents(
        _COLLECTION,
        filters=[("ownerUid", "==", owner_uid), ("archivedAt", "==", None)],
        order_by="lastMessageAt",
        order_direction="DESCENDING",
        limit=limit,
    )
    return [idx for _, idx in _hydrate_rows(rows)]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_document(idx: ChatSessionIndex) -> dict:
    """Convert a ChatSessionIndex to a backend-neutral JSON-friendly dict."""
    data = idx.model_dump(by_alias=True, exclude_none=False)
    for key in ("firstMessageAt", "lastMessageAt", "archivedAt"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    if "accessControl" in data and hasattr(data["accessControl"], "model_dump"):
        data["accessControl"] = data["accessControl"].model_dump(exclude_none=True)
    return data


def _from_document(data: dict, doc_id: str) -> ChatSessionIndex:
    """Hydrate a ChatSessionIndex from a repository document."""
    clean = {key: value for key, value in data.items() if key != "__id"}
    if "sessionId" not in clean:
        clean = {**clean, "sessionId": doc_id}
    return ChatSessionIndex.model_validate(clean)


# Backward-compatible internal aliases for tests/tools that imported the old
# Firestore-named serializer helpers.
_to_firestore = _to_document
_from_firestore = _from_document
