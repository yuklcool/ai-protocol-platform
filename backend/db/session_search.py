"""Owner-scoped session metadata search and filter-bound keyset cursors.

No transcript scan or inferred Run status. PostgreSQL executes predicates and
LIMIT in SQL; memory/Firestore share the same metadata matching semantics.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from db.models.chat_session import ChatSessionIndex
from observability.user_context import require_resource_user

log = logging.getLogger(__name__)
Position = tuple[datetime, str]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Search timestamps must include a timezone")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class SessionSearch:
    owner_uid: str
    query: str = ""
    skill_id: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None

    def __post_init__(self):
        if not self.owner_uid:
            raise ValueError("Session owner is required")
        object.__setattr__(self, "query", self.query.strip().lower())
        if len(self.query) > 200:
            raise ValueError("Search query is too long")
        for field in ("updated_after", "updated_before"):
            if value := getattr(self, field):
                object.__setattr__(self, field, utc(value))
        if self.updated_after and self.updated_before and self.updated_after >= self.updated_before:
            raise ValueError("Search start must precede end")

    def scope(self) -> str:
        values = [
            self.owner_uid,
            self.query,
            self.skill_id,
            self.updated_after.isoformat() if self.updated_after else None,
            self.updated_before.isoformat() if self.updated_before else None,
        ]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()

    def decode_cursor(self, cursor: str | None) -> Position | None:
        if not cursor:
            return None
        try:
            if len(cursor) > 2048:
                raise ValueError
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            data = json.loads(raw)
            if data["v"] != 1 or data["s"] != self.scope() or not isinstance(data["i"], str) or not data["i"]:
                raise ValueError
            return utc(datetime.fromisoformat(data["t"])), data["i"]
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise ValueError("Invalid cursor for these search filters") from exc

    def encode_cursor(self, position: Position) -> str:
        payload = {"v": 1, "s": self.scope(), "t": utc(position[0]).isoformat(), "i": position[1]}
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def position(row: dict) -> Position:
    value = row["lastMessageAt"]
    return utc(value if isinstance(value, datetime) else datetime.fromisoformat(value)), row["__id"]


def match_rows(rows: list[dict], search: SessionSearch, after: Position | None, limit: int) -> list[dict]:
    """Fallback for memory and Firestore's owner-filtered server-side scan."""
    matches = []
    for row in rows:
        if row.get("ownerUid") != search.owner_uid or row.get("archivedAt") or row.get("provisional"):
            continue
        if search.skill_id is not None and row.get("skillId") != search.skill_id:
            continue
        if search.query and not any(
            search.query in str(value or "").lower() for value in (row.get("title"), row["__id"])
        ):
            continue
        try:
            key = position(row)
        except (ValueError, TypeError, KeyError):
            log.warning("Invalid timestamp on chat session %s", row.get("__id"))
            continue
        if search.updated_after and key[0] < search.updated_after:
            continue
        if search.updated_before and key[0] >= search.updated_before:
            continue
        if after is not None and key >= after:
            continue
        matches.append(row)
    return sorted(matches, key=position, reverse=True)[:limit]


def search_sessions(search: SessionSearch, *, page_size: int = 20, cursor: str | None = None):
    from db.persistence import get_repository

    require_resource_user(search.owner_uid)
    if not 1 <= page_size <= 50:
        raise ValueError("Page size must be between 1 and 50")
    after = search.decode_cursor(cursor)
    results: list[tuple[dict, ChatSessionIndex]] = []
    # Skip malformed non-timestamp metadata without truncating a page or losing
    # its continuation. Cursors seek values, never re-read a foreign document.
    while len(results) <= page_size:
        rows = get_repository().search_chat_sessions(search, after=after, limit=page_size + 1)
        for row in rows:
            try:
                idx = ChatSessionIndex.model_validate({**row, "sessionId": row["__id"]})
            except ValueError:
                log.warning("Malformed chat session metadata %s", row["__id"])
                continue
            results.append((row, idx))
        if len(rows) < page_size + 1 or len(results) > page_size:
            break
        after = position(rows[-1])
    next_cursor = search.encode_cursor(position(results[page_size - 1][0])) if len(results) > page_size else None
    return [idx for _, idx in results[:page_size]], next_cursor
