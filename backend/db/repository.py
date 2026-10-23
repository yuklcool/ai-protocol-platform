"""Backend-neutral persistence contract.

Business/domain modules should depend on :class:`Repository`, not on the
Firestore SDK. The contract mirrors the document operations the platform uses
while preserving concurrency-sensitive semantics and cursor pagination across
memory, Firestore, and PostgreSQL backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from db.session_search import Position, SessionSearch

Filter = tuple[str, str, Any]


@runtime_checkable
class Repository(Protocol):
    """Minimal document repository shared by memory, Firestore and Postgres."""

    def create_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> bool:
        """Atomically insert only if absent; return False when already present."""
        ...

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None: ...

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None: ...

    def delete_document(self, collection: str, doc_id: str) -> None: ...

    def query_documents(
        self,
        collection: str,
        *,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        start_after_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None: ...

    def search_chat_sessions(
        self, search: SessionSearch, *, after: Position | None, limit: int
    ) -> list[dict[str, Any]]: ...

    def array_union_field(
        self,
        collection: str,
        doc_id: str,
        field: str,
        values: list[Any],
    ) -> None: ...

    def healthcheck(self) -> bool: ...
