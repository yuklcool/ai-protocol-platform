"""Durable ADK memory backed by the existing PostgreSQL document repository.

The goal is deliberately small: preserve the semantics of ADK's
``InMemoryMemoryService`` (event ingestion + keyword recall) while making the
memory survive backend restarts.  It does *not* introduce embeddings, a vector
DB, Redis, or another service.  Semantic/vector recall can be layered on later
with PostgreSQL/pgvector without changing the ADK service boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from google.adk.events import Event
from google.adk.memory import BaseMemoryService
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from typing_extensions import override

from db.repository import Repository

if TYPE_CHECKING:
    from google.adk.sessions import Session

_UNKNOWN_SESSION_ID = "__unknown_session_id__"
_COLLECTION_PREFIX = "adk_memory_events"


def _scope_collection(app_name: str, user_id: str) -> str:
    """Return a stable per-app/per-user collection partition.

    ``PostgresRepository`` stores documents by (collection, doc_id). Partitioning
    memory at the collection level means a recall only scans this user's rows,
    rather than every tenant/user memory row in the deployment.
    """
    digest = hashlib.sha256(f"{app_name}\0{user_id}".encode()).hexdigest()[:32]
    return f"{_COLLECTION_PREFIX}_{digest}"


def _event_doc_id(session_id: str, event: Event, index: int = 0) -> str:
    event_id = event.id or f"event-{index}"
    return hashlib.sha256(f"{session_id}\0{event_id}".encode()).hexdigest()


def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return " ".join(part.text for part in event.content.parts if part.text)


def _words(text: str) -> set[str]:
    # Unicode-aware ``\w`` keeps this usable for non-English text too. The
    # substring fallback in _matches covers languages without whitespace word
    # boundaries (for example Chinese).
    return {word.casefold() for word in re.findall(r"\w+", text, flags=re.UNICODE)}


def _matches(query: str, text: str) -> bool:
    normalized_query = query.strip().casefold()
    normalized_text = text.casefold()
    if not normalized_query or not normalized_text:
        return False
    if normalized_query in normalized_text:
        return True
    query_words = _words(query)
    event_words = _words(text)
    return bool(query_words and event_words and query_words.intersection(event_words))


def _format_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    except (OverflowError, OSError, TypeError, ValueError):
        return None


class PostgresMemoryService(BaseMemoryService):
    """ADK ``BaseMemoryService`` persisted in the platform PostgreSQL database.

    A Repository may be injected by tests. Runtime construction uses the same
    ``DATABASE_URL`` and ``PostgresRepository`` already used by the platform,
    so this feature adds no infrastructure component.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        repository: Repository | None = None,
    ) -> None:
        if repository is None:
            from db.repositories.postgres import PostgresRepository

            url = (database_url or os.environ.get("DATABASE_URL", "")).strip()
            if not url:
                raise RuntimeError("DATABASE_URL is required for PostgreSQL memory")
            repository = PostgresRepository(url)
        self._repository = repository
        try:
            self._scan_limit = max(1, int(os.environ.get("MEMORY_SEARCH_SCAN_LIMIT", "2000")))
        except ValueError:
            self._scan_limit = 2000

    @staticmethod
    def _serialise_event(
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        event: Event,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        return {
            "appName": app_name,
            "userId": user_id,
            "sessionId": session_id,
            "eventId": event.id,
            "timestamp": event.timestamp,
            "text": _event_text(event),
            "event": event.model_dump(mode="json"),
            "customMetadata": dict(custom_metadata or {}),
        }

    def _replace_session_sync(self, session: Session) -> None:
        collection = _scope_collection(session.app_name, session.user_id)
        existing = self._repository.query_documents(
            collection,
            filters=[("sessionId", "==", session.id)],
        )
        for row in existing:
            doc_id = row.get("__id")
            if isinstance(doc_id, str):
                self._repository.delete_document(collection, doc_id)

        events = [event for event in session.events if event.content and event.content.parts]
        for index, event in enumerate(events):
            self._repository.set_document(
                collection,
                _event_doc_id(session.id, event, index),
                self._serialise_event(
                    app_name=session.app_name,
                    user_id=session.user_id,
                    session_id=session.id,
                    event=event,
                ),
            )

    @override
    async def add_session_to_memory(self, session: Session) -> None:
        # Repository is synchronous by contract; move the whole replacement off
        # the request event loop rather than blocking streaming while DB I/O runs.
        await asyncio.to_thread(self._replace_session_sync, session)

    def _add_events_sync(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: str,
        custom_metadata: Mapping[str, object] | None,
    ) -> None:
        collection = _scope_collection(app_name, user_id)
        for index, event in enumerate(events):
            if not event.content or not event.content.parts:
                continue
            self._repository.set_document(
                collection,
                _event_doc_id(session_id, event, index),
                self._serialise_event(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    event=event,
                    custom_metadata=custom_metadata,
                ),
            )

    @override
    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        scoped_session_id = session_id or _UNKNOWN_SESSION_ID
        await asyncio.to_thread(
            self._add_events_sync,
            app_name=app_name,
            user_id=user_id,
            events=events,
            session_id=scoped_session_id,
            custom_metadata=custom_metadata,
        )

    def _search_sync(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        collection = _scope_collection(app_name, user_id)
        rows = self._repository.query_documents(
            collection,
            order_by="timestamp",
            order_direction="DESCENDING",
            limit=self._scan_limit,
        )
        response = SearchMemoryResponse()
        for row in rows:
            text = str(row.get("text") or "")
            if not _matches(query, text):
                continue
            raw_event = row.get("event")
            if not isinstance(raw_event, dict):
                continue
            try:
                event = Event.model_validate(raw_event)
            except Exception:
                # One malformed historic row must not make all recall fail.
                continue
            if not event.content or not event.content.parts:
                continue
            response.memories.append(
                MemoryEntry(
                    id=str(row.get("eventId") or row.get("__id") or "") or None,
                    content=event.content,
                    author=event.author,
                    timestamp=_format_timestamp(event.timestamp),
                    custom_metadata=dict(row.get("customMetadata") or {}),
                )
            )
        return response

    @override
    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        return await asyncio.to_thread(
            self._search_sync,
            app_name=app_name,
            user_id=user_id,
            query=query,
        )
