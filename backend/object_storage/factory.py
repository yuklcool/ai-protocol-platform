"""Object storage backend selection.

The selector is intentionally independent from GCP/ADK configuration.  New
business code should depend on ``get_object_storage()`` and the ObjectStorage
contract rather than importing a provider SDK directly.
"""

from __future__ import annotations

import os

from object_storage.base import ObjectStorage
from object_storage.local import LocalObjectStorage

_SUPPORTED_BACKENDS = {"local", "gcs", "s3"}
_storage_singleton: ObjectStorage | None = None
_storage_signature: tuple[str, str] | None = None


def object_storage_backend_name() -> str:
    value = os.environ.get("OBJECT_STORAGE_BACKEND", "local").strip().lower() or "local"
    if value not in _SUPPORTED_BACKENDS:
        raise RuntimeError(
            f"Unsupported OBJECT_STORAGE_BACKEND={value!r}; expected local, gcs, or s3"
        )
    return value


def get_object_storage() -> ObjectStorage:
    """Return the configured storage adapter.

    Phase 2 starts with the zero-component local backend. GCS/S3 are named now so
    deployment configuration is stable, but are activated only after their
    adapters are wired; failing loudly is safer than silently writing local data
    when an operator explicitly requested remote storage.
    """
    global _storage_singleton, _storage_signature
    backend = object_storage_backend_name()
    root = os.environ.get("OBJECT_STORAGE_LOCAL_ROOT", "/data/objects").strip() or "/data/objects"
    signature = (backend, root)
    if _storage_singleton is not None and _storage_signature == signature:
        return _storage_singleton

    if backend == "local":
        _storage_singleton = LocalObjectStorage(root)
    elif backend == "gcs":
        raise RuntimeError("OBJECT_STORAGE_BACKEND=gcs adapter is not wired yet")
    else:
        raise RuntimeError("OBJECT_STORAGE_BACKEND=s3 adapter is not wired yet")
    _storage_signature = signature
    return _storage_singleton


def _reset_object_storage_for_tests() -> None:
    global _storage_singleton, _storage_signature
    _storage_singleton = None
    _storage_signature = None
