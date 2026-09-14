"""Folder configuration — backend-neutral CRUD for bucket folder records.

For Firestore compatibility the collection key remains the existing nested path
``buckets/{bucketId}/folders``. PostgreSQL stores that same path as the logical
collection key, so no business-model or Firestore data-layout migration is
required.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from db import persistence as fs
from db.models import AccessControl, BucketConfig, BucketFolderConfig

_FOLDERS_SUBCOLLECTION = "folders"


def _folder_collection(bucket_id: str) -> str:
    return f"buckets/{bucket_id}/{_FOLDERS_SUBCOLLECTION}"


def _to_firestore(config: BucketFolderConfig) -> dict[str, Any]:
    return config.model_dump(by_alias=True)


def _from_firestore(data: dict[str, Any]) -> BucketFolderConfig:
    data.pop("__id", None)
    return BucketFolderConfig.model_validate(data)


def compute_effective_access(
    folder_access: AccessControl | dict[str, Any] | None,
    parent: BucketConfig,
) -> AccessControl:
    """Resolve effective access at write time."""
    if folder_access is None:
        return parent.access_control
    if isinstance(folder_access, AccessControl):
        return folder_access
    return AccessControl.model_validate(folder_access)


def create_folder(
    bucket: BucketConfig,
    path: str,
    display_name: str,
    owner_id: str,
    access_control: AccessControl | dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> BucketFolderConfig:
    """Create a new folder under `bucket`."""
    folder_id = str(uuid.uuid4())
    now = time.time()
    effective = compute_effective_access(access_control, bucket)
    config = BucketFolderConfig(
        folderId=folder_id,
        bucketId=bucket.bucket_id,
        path=path,
        displayName=display_name,
        ownerId=owner_id,
        accessControl=access_control
        if access_control is None or isinstance(access_control, AccessControl)
        else AccessControl.model_validate(access_control),
        effectiveAccess=effective,
        tags=tags or [],
        createdAt=now,
        updatedAt=now,
    )
    fs.set_document(
        _folder_collection(bucket.bucket_id),
        folder_id,
        _to_firestore(config),
    )
    return config


def get_folder(bucket_id: str, folder_id: str) -> BucketFolderConfig | None:
    data = fs.get_document(_folder_collection(bucket_id), folder_id)
    if data is None:
        return None
    return _from_firestore(data)


def update_folder(
    bucket: BucketConfig,
    folder_id: str,
    updates: dict[str, Any],
) -> BucketFolderConfig | None:
    """Update a folder. Recomputes effective_access if accessControl changed."""
    existing = get_folder(bucket.bucket_id, folder_id)
    if existing is None:
        return None

    if "accessControl" in updates:
        effective = compute_effective_access(updates["accessControl"], bucket)
        updates["effectiveAccess"] = effective.model_dump()
    updates["updatedAt"] = time.time()
    fs.update_document(_folder_collection(bucket.bucket_id), folder_id, updates)
    return get_folder(bucket.bucket_id, folder_id)


def delete_folder(bucket_id: str, folder_id: str) -> bool:
    if get_folder(bucket_id, folder_id) is None:
        return False
    fs.delete_document(_folder_collection(bucket_id), folder_id)
    return True


def list_folders(bucket_id: str, limit: int = 50) -> list[BucketFolderConfig]:
    """List folders under a bucket ordered by most recently updated."""
    docs = fs.query_documents(
        _folder_collection(bucket_id),
        order_by="updatedAt",
        order_direction="DESCENDING",
        limit=limit,
    )
    return [_from_firestore(doc) for doc in docs]
