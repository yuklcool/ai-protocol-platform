"""User-facing document folder CRUD on the backend-neutral repository.

New records live in the flat ``document_folders`` collection so Memory,
Firestore and PostgreSQL share one model. Folder contents are derived from the
canonical ``parsed_documents`` collection instead of maintaining a second
nested document index.

Cloud deployments may still have historical Firestore data under
``users/{uid}/folders/{folderId}``; read/count helpers retain a narrow legacy
fallback when DATA_BACKEND=firestore so the self-host migration does not make
existing cloud folders disappear.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from db.persistence import data_backend, get_document, increment_field, query_documents, set_document

_FOLDER_COLLECTION = "document_folders"
_PARSED_DOCS_COLLECTION = "parsed_documents"


class Folder(BaseModel):
    id: str
    name: str
    user_id: str = Field(alias="userId")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    doc_count: int = Field(default=0, alias="docCount")
    parsed_count: int = Field(default=0, alias="parsedCount")

    model_config = ConfigDict(populate_by_name=True)


def _legacy_folders_ref(user_id: str):
    from db.firestore import get_client

    return get_client().collection("users").document(user_id).collection("folders")


def _legacy_get_folder(user_id: str, folder_id: str) -> dict[str, Any] | None:
    if data_backend() != "firestore":
        return None
    doc = _legacy_folders_ref(user_id).document(folder_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data.setdefault("id", folder_id)
    return data


def create_folder(user_id: str, name: str) -> dict[str, Any]:
    folder_id = str(uuid.uuid4())
    data: dict[str, Any] = {
        "id": folder_id,
        "name": name,
        "userId": user_id,
        "createdAt": datetime.now(UTC).isoformat(),
        "docCount": 0,
        "parsedCount": 0,
    }
    set_document(_FOLDER_COLLECTION, folder_id, data)
    return {k: data[k] for k in ("id", "name", "userId", "docCount", "parsedCount")}


def get_folder(user_id: str, folder_id: str) -> dict[str, Any] | None:
    data = get_document(_FOLDER_COLLECTION, folder_id)
    if data is not None:
        if data.get("userId") != user_id:
            return None
        data.setdefault("id", folder_id)
        return data
    return _legacy_get_folder(user_id, folder_id)


def list_folders(user_id: str) -> list[dict[str, Any]]:
    current = query_documents(
        _FOLDER_COLLECTION,
        filters=[("userId", "==", user_id)],
        order_by="createdAt",
        order_direction="ASCENDING",
    )
    by_id: dict[str, dict[str, Any]] = {}
    for item in current:
        folder_id = str(item.get("id") or item.get("__id") or "")
        if not folder_id:
            continue
        item["id"] = folder_id
        by_id[folder_id] = item

    if data_backend() == "firestore":
        for doc in _legacy_folders_ref(user_id).stream():
            if doc.id in by_id:
                continue
            data = doc.to_dict() or {}
            data.setdefault("id", doc.id)
            by_id[doc.id] = data

    return list(by_id.values())


def list_folder_documents(user_id: str, folder_id: str) -> list[dict[str, Any]]:
    """Return the canonical parsed-document records assigned to this folder."""
    return query_documents(
        _PARSED_DOCS_COLLECTION,
        filters=[("userId", "==", user_id), ("folderId", "==", folder_id)],
        order_by="createdAt",
        order_direction="DESCENDING",
    )


def update_folder_counts(user_id: str, folder_id: str, doc_delta: int = 0, parsed_delta: int = 0) -> None:
    current = get_document(_FOLDER_COLLECTION, folder_id)
    if current is not None and current.get("userId") == user_id:
        if doc_delta:
            increment_field(_FOLDER_COLLECTION, folder_id, "docCount", doc_delta)
        if parsed_delta:
            increment_field(_FOLDER_COLLECTION, folder_id, "parsedCount", parsed_delta)
        return

    if data_backend() == "firestore":
        # Historical cloud folders were nested and cannot be represented by the
        # generic Repository contract. Keep count updates working until those
        # records are lazily/explicitly migrated to document_folders.
        from google.cloud.firestore import Increment

        updates: dict[str, Any] = {}
        if doc_delta:
            updates["docCount"] = Increment(doc_delta)
        if parsed_delta:
            updates["parsedCount"] = Increment(parsed_delta)
        if updates:
            _legacy_folders_ref(user_id).document(folder_id).update(updates)


def ensure_default_folder(user_id: str) -> str:
    folders = list_folders(user_id)
    if folders:
        return str(folders[0]["id"])
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return str(create_folder(user_id, f"Uploads {today}")["id"])
