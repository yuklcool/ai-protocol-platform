"""In-memory repository used by LOCAL_MODE and persistence contract tests.

In LOCAL_MODE this adapter deliberately wraps the *existing*
``InMemoryFirestoreClient`` singleton used by the fixture seeder.  That keeps
seeded Skills/users/documents visible while business modules move from
``db.firestore`` to ``db.persistence``.  Outside LOCAL_MODE it creates an
isolated in-memory client, which is convenient for contract tests.
"""

from __future__ import annotations

from typing import Any

from config.local_mode import is_local_mode
from db.repositories._document_ops import apply_query
from db.repository import Filter


class MemoryRepository:
    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
        elif is_local_mode():
            # Reuse the singleton seeded by db.local_fixture.
            from db.firestore import get_client

            self._client = get_client()
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

    def healthcheck(self) -> bool:
        return True
