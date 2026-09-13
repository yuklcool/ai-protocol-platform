"""Backend-neutral persistence contract.

Business/domain modules should depend on :class:`Repository`, not on the
Firestore SDK.  The first contract deliberately mirrors the small document
operations the platform already uses so migration can happen domain-by-domain
without a flag-day rewrite.

The contract is intentionally synchronous because the existing Skill/Admin/
Tenant persistence call sites are synchronous today.  Backends own their
connection/pooling strategy behind this boundary.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

Filter = tuple[str, str, Any]


@runtime_checkable
class Repository(Protocol):
    """Minimal document repository shared by memory, Firestore and Postgres."""

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
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None: ...

    def healthcheck(self) -> bool: ...
