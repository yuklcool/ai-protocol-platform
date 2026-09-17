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
_storage_signature: tuple[str, ...] | None = None


def object_storage_backend_name() -> str:
    value = os.environ.get("OBJECT_STORAGE_BACKEND", "local").strip().lower() or "local"
    if value not in _SUPPORTED_BACKENDS:
        raise RuntimeError(
            f"Unsupported OBJECT_STORAGE_BACKEND={value!r}; expected local, gcs, or s3"
        )
    return value


def get_object_storage() -> ObjectStorage:
    """Return the configured storage adapter.

    ``local`` remains the zero-component self-host default. ``gcs`` and ``s3``
    are explicit opt-in provider adapters. Requesting a remote adapter with
    incomplete configuration fails loudly rather than silently writing to local
    disk and creating split-brain object data.
    """
    global _storage_singleton, _storage_signature
    backend = object_storage_backend_name()

    if backend == "local":
        root = os.environ.get("OBJECT_STORAGE_LOCAL_ROOT", "/data/objects").strip() or "/data/objects"
        signature: tuple[str, ...] = (backend, root)
    elif backend == "gcs":
        bucket = os.environ.get("OBJECT_STORAGE_GCS_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("OBJECT_STORAGE_GCS_BUCKET is required when OBJECT_STORAGE_BACKEND=gcs")
        signature = (backend, bucket)
    else:
        bucket = os.environ.get("OBJECT_STORAGE_S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("OBJECT_STORAGE_S3_BUCKET is required when OBJECT_STORAGE_BACKEND=s3")
        endpoint = os.environ.get("OBJECT_STORAGE_S3_ENDPOINT", "").strip()
        region = os.environ.get("OBJECT_STORAGE_S3_REGION", "us-east-1").strip() or "us-east-1"
        access_key = os.environ.get("OBJECT_STORAGE_S3_ACCESS_KEY", "").strip()
        secret_key = os.environ.get("OBJECT_STORAGE_S3_SECRET_KEY", "").strip()
        session_token = os.environ.get("OBJECT_STORAGE_S3_SESSION_TOKEN", "").strip()
        addressing_style = os.environ.get("OBJECT_STORAGE_S3_ADDRESSING_STYLE", "auto").strip().lower() or "auto"
        if bool(access_key) != bool(secret_key):
            raise RuntimeError(
                "OBJECT_STORAGE_S3_ACCESS_KEY and OBJECT_STORAGE_S3_SECRET_KEY must be configured together"
            )
        if session_token and not access_key:
            raise RuntimeError("OBJECT_STORAGE_S3_SESSION_TOKEN requires explicit S3 access/secret keys")
        signature = (
            backend,
            bucket,
            endpoint,
            region,
            access_key,
            secret_key,
            session_token,
            addressing_style,
        )

    if _storage_singleton is not None and _storage_signature == signature:
        return _storage_singleton

    if backend == "local":
        _storage_singleton = LocalObjectStorage(root)
    elif backend == "gcs":
        from object_storage.gcs import GcsObjectStorage

        _storage_singleton = GcsObjectStorage(bucket)
    else:
        from object_storage.s3 import S3ObjectStorage

        _storage_singleton = S3ObjectStorage(
            bucket,
            endpoint_url=endpoint or None,
            region_name=region,
            access_key_id=access_key or None,
            secret_access_key=secret_key or None,
            session_token=session_token or None,
            addressing_style=addressing_style,
        )

    _storage_signature = signature
    return _storage_singleton


def _reset_object_storage_for_tests() -> None:
    global _storage_singleton, _storage_signature
    _storage_singleton = None
    _storage_signature = None
