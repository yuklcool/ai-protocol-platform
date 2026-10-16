"""Provider-neutral object storage package."""

from object_storage.base import ObjectInfo, ObjectStorage
from object_storage.factory import get_object_storage, object_storage_backend_name
from object_storage.local import LocalObjectStorage, StoragePathError

__all__ = [
    "LocalObjectStorage",
    "ObjectInfo",
    "ObjectStorage",
    "StoragePathError",
    "get_object_storage",
    "object_storage_backend_name",
]
