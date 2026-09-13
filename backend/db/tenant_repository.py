"""Tenant-scoped persistence guard.

This wrapper is intentionally backend-neutral: it sits above the Repository
contract and therefore applies the same isolation rules to memory, Firestore,
and PostgreSQL. New tenant-owned domain code should request a scoped repository
instead of manually remembering to append a tenant filter on every query.

Existing legacy collections are not switched automatically; migration can happen
one domain at a time without changing current behavior.
"""

from __future__ import annotations

from typing import Any

from db.repository import Filter, Repository


class TenantIsolationError(PermissionError):
    """Raised when a scoped operation targets a document owned by another tenant."""


class TenantRepository:
    """Repository view that enforces a single ``tenantId`` value.

    Reads fail closed: a document without ``tenantId`` is not visible through a
    tenant-scoped repository. Writes inject the scoped tenant id and reject an
    explicitly conflicting value.
    """

    def __init__(self, repository: Repository, tenant_id: str, *, tenant_field: str = "tenantId") -> None:
        tenant_id = tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty")
        self._repository = repository
        self.tenant_id = tenant_id
        self.tenant_field = tenant_field

    def _assert_owned(self, collection: str, doc_id: str, document: dict[str, Any] | None) -> dict[str, Any] | None:
        if document is None:
            return None
        if document.get(self.tenant_field) != self.tenant_id:
            raise TenantIsolationError(
                f"{collection}/{doc_id} is not owned by tenant {self.tenant_id!r}"
            )
        return document

    def _scoped_data(self, data: dict[str, Any]) -> dict[str, Any]:
        explicit = data.get(self.tenant_field)
        if explicit is not None and explicit != self.tenant_id:
            raise TenantIsolationError(
                f"write tenant {explicit!r} conflicts with scoped tenant {self.tenant_id!r}"
            )
        return {**data, self.tenant_field: self.tenant_id}

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        return self._assert_owned(collection, doc_id, self._repository.get_document(collection, doc_id))

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None:
        if merge:
            existing = self._repository.get_document(collection, doc_id)
            if existing is not None:
                self._assert_owned(collection, doc_id, existing)
        self._repository.set_document(collection, doc_id, self._scoped_data(data), merge=merge)

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        existing = self._assert_owned(collection, doc_id, self._repository.get_document(collection, doc_id))
        if existing is None:
            return
        self._repository.update_document(collection, doc_id, self._scoped_data(data))

    def delete_document(self, collection: str, doc_id: str) -> None:
        existing = self._assert_owned(collection, doc_id, self._repository.get_document(collection, doc_id))
        if existing is None:
            return
        self._repository.delete_document(collection, doc_id)

    def query_documents(
        self,
        collection: str,
        *,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        start_after_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        scoped_filters: list[Filter] = [(self.tenant_field, "==", self.tenant_id)]
        if filters:
            for field, op, value in filters:
                if field == self.tenant_field and (op != "==" or value != self.tenant_id):
                    raise TenantIsolationError("query attempted to override tenant scope")
                if field != self.tenant_field:
                    scoped_filters.append((field, op, value))
        return self._repository.query_documents(
            collection,
            filters=scoped_filters,
            order_by=order_by,
            order_direction=order_direction,
            start_after_id=start_after_id,
            limit=limit,
        )

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        existing = self._assert_owned(collection, doc_id, self._repository.get_document(collection, doc_id))
        if existing is None:
            return
        self._repository.increment_field(collection, doc_id, field, amount)

    def array_union_field(
        self,
        collection: str,
        doc_id: str,
        field: str,
        values: list[Any],
    ) -> None:
        existing = self._assert_owned(collection, doc_id, self._repository.get_document(collection, doc_id))
        if existing is None:
            return
        self._repository.array_union_field(collection, doc_id, field, values)

    def healthcheck(self) -> bool:
        return self._repository.healthcheck()
