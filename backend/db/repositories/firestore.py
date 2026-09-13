"""Firestore implementation of the backend-neutral repository contract."""

from __future__ import annotations

from typing import Any

from google.cloud import firestore

from config.gcp import resolve_gcp_project
from db.repository import Filter


class FirestoreRepository:
    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            project = resolve_gcp_project()
            self._client = firestore.Client(project=project) if project else firestore.Client()

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
        self._client.collection(collection).document(doc_id).update(data)

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
        query = self._client.collection(collection)
        if filters:
            for field, op, value in filters:
                query = query.where(filter=firestore.FieldFilter(field, op, value))
        if order_by:
            direction = (
                firestore.Query.DESCENDING
                if order_direction.upper() == "DESCENDING"
                else firestore.Query.ASCENDING
            )
            query = query.order_by(order_by, direction=direction)
        if limit is not None:
            query = query.limit(limit)

        result: list[dict[str, Any]] = []
        for doc in query.stream():
            data = doc.to_dict()
            if data is not None:
                data["__id"] = doc.id
                result.append(data)
        return result

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        self._client.collection(collection).document(doc_id).update({field: firestore.Increment(amount)})

    def healthcheck(self) -> bool:
        # Avoid creating/deleting sentinel documents. Reading a bounded query is
        # enough to prove credentials/project/connectivity for readiness checks.
        next(iter(self._client.collection("__persistence_health").limit(1).stream()), None)
        return True
