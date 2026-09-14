"""Object storage backend selection.

The selector is intentionally independent from GCP/ADK configuration. New
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

    ``local`` is the zero-component self-host default. ``gcs`` keeps the cloud
    deployment path available behind the same contract. ``s3`` is intentionally
    fail-loud until its adapter is implemented; silently falling back to local
    when an operator requested remote storage would create split-brain data.
    """
    global _storage_singleton, _storage_signature
    backend = object_storage_backend_name()
    if backend == "local":
        config = os.environ.get("OBJECT_STORAGE_LOCAL_ROOT", "/data/objects").strip() or "/data/objects"
    elif backend == "gcs":
        config = os.environ.get("OBJECT_STORAGE_GCS_BUCKET", "").strip()
        if not config:
            raise RuntimeError("OBJECT_STORAGE_GCS_BUCKET is required when OBJECT_STORAGE_BACKEND=gcs")
    else:
        config = os.environ.get("OBJECT_STORAGE_S3_BUCKET", "").strip()

    signature = (backend, config)
    if _storage_singleton is not None and _storage_signature == signature:
        return _storage_singleton

    if backend == "local":
        _storage_singleton = LocalObjectStorage(config)
    elif backend == "gcs":
        from object_storage.gcs import GcsObjectStorage

        _storage_singleton = GcsObjectStorage(config)
    else:
        raise RuntimeError("OBJECT_STORAGE_BACKEND=s3 adapter is not wired yet")
    _storage_signature = signature
    return _storage_singleton


def _reset_object_storage_for_tests() -> None:
    global _storage_singleton, _storage_signature
    _storage_singleton = None
    _storage_signature = None
