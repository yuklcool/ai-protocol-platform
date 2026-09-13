"""In-memory repository used by LOCAL_MODE and persistence contract tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from db.repositories._document_ops import apply_query
from db.repository import Filter


class MemoryRepository:
    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}

    def _collection(self, name: str) -> dict[str, dict[str, Any]]:
        return self._collections.setdefault(name, {})

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        value = self._collection(collection).get(doc_id)
        return deepcopy(value) if value is not None else None

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None:
        target = self._collection(collection)
        if merge and doc_id in target:
            target[doc_id] = {**target[doc_id], **deepcopy(data)}
        else:
            target[doc_id] = deepcopy(data)

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        target = self._collection(collection)
        if doc_id not in target:
            raise KeyError(f"document {collection}/{doc_id} does not exist")
        target[doc_id].update(deepcopy(data))

    def delete_document(self, collection: str, doc_id: str) -> None:
        self._collection(collection).pop(doc_id, None)

    def query_documents(
        self,
        collection: str,
        *,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        docs = []
        for doc_id, value in self._collection(collection).items():
            data = deepcopy(value)
            data["__id"] = doc_id
            docs.append(data)
        return apply_query(
            docs,
            filters=filters,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
        )

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        target = self._collection(collection)
        if doc_id not in target:
            raise KeyError(f"document {collection}/{doc_id} does not exist")
        current = target[doc_id].get(field, 0)
        if not isinstance(current, (int, float)):
            raise TypeError(f"field {field!r} on {collection}/{doc_id} is not numeric")
        target[doc_id][field] = current + amount

    def healthcheck(self) -> bool:
        return True
