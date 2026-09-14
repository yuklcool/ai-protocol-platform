"""In-memory repository used by LOCAL_MODE and persistence contract tests.

``MemoryRepository()`` is intentionally an isolated repository instance.  The
LOCAL_MODE fixture store is shared only when the persistence factory explicitly
injects ``db.firestore.get_client()``.  Keeping that choice out of this adapter
prevents environment variables from silently changing repository semantics in
unit tests, migration tools, tenant wrappers, or other direct callers.
"""

from __future__ import annotations

from typing import Any

from db.repositories._document_ops import apply_query
from db.repository import Filter


class MemoryRepository:
    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            from db.firestore_inmemory import InMemoryFirestoreClient

            self._client = InMemoryFirestoreClient()

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._client.collection(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None:
        self._client.collection(collection).document(doc_id).set(data, merge=merge)

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        ref = self._client.collection(collection).document(doc_id)
        if not ref.get().exists:
            raise KeyError(f"document {collection}/{doc_id} does not exist")
        ref.update(data)

    def delete_document(self, collection: str, doc_id: str) -> None:
        self._client.collection(collection).document(doc_id).delete()

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
        docs: list[dict[str, Any]] = []
        for snapshot in self._client.collection(collection).stream():
            data = snapshot.to_dict()
            if data is not None:
                data["__id"] = snapshot.id
                docs.append(data)
        return apply_query(
            docs,
            filters=filters,
            order_by=order_by,
            order_direction=order_direction,
            start_after_id=start_after_id,
            limit=limit,
        )

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        ref = self._client.collection(collection).document(doc_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(f"document {collection}/{doc_id} does not exist")
        data = snapshot.to_dict() or {}
        current = data.get(field, 0)
        if not isinstance(current, (int, float)):
            raise TypeError(f"field {field!r} on {collection}/{doc_id} is not numeric")
        ref.update({field: current + amount})

    def array_union_field(
        self,
        collection: str,
        doc_id: str,
        field: str,
        values: list[Any],
    ) -> None:
        if not values:
            return
        ref = self._client.collection(collection).document(doc_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(f"document {collection}/{doc_id} does not exist")
        data = snapshot.to_dict() or {}
        current = data.get(field, [])
        if current is None:
            current = []
        if not isinstance(current, list):
            raise TypeError(f"field {field!r} on {collection}/{doc_id} is not an array")
        merged = list(current)
        for value in values:
            if value not in merged:
                merged.append(value)
        ref.update({field: merged})

    def healthcheck(self) -> bool:
        return True
