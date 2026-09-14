"""ADK ArtifactService backend selection for self-host and cloud deployments.

This module keeps artifact policy separate from Session/Memory policy.  Local
self-hosting reuses the persistent ``/data`` volume through ADK's own
``FileArtifactService``; cloud deployments can continue using GCS; memory stays
available for tests and source-only development.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.artifacts.base_artifact_service import BaseArtifactService
from google.adk.artifacts.file_artifact_service import FileArtifactService

ArtifactService = BaseArtifactService

_service_singleton: ArtifactService | None = None
_service_signature: tuple[str, str] | None = None


def artifact_backend_name() -> str:
    """Resolve ``memory|local|gcs`` while preserving old cloud behaviour."""
    explicit = os.environ.get("ARTIFACT_BACKEND", "").strip().lower()
    if explicit:
        if explicit not in {"memory", "local", "gcs"}:
            raise RuntimeError(
                f"Unsupported ARTIFACT_BACKEND={explicit!r}; expected memory, local, or gcs"
            )
        return explicit

    object_backend = os.environ.get("OBJECT_STORAGE_BACKEND", "").strip().lower()
    if object_backend == "local":
        return "local"
    if object_backend == "gcs":
        return "gcs"

    # Backwards compatibility for existing cloud deployments that only set the
    # historical ADK bucket variable.
    if os.environ.get("ADK_ARTIFACT_BUCKET", "").strip():
        return "gcs"
    return "memory"


def _local_root() -> str:
    return os.environ.get("ADK_ARTIFACT_ROOT", "/data/artifacts").strip() or "/data/artifacts"


def _gcs_bucket() -> str:
    bucket = (
        os.environ.get("ADK_ARTIFACT_BUCKET")
        or os.environ.get("OBJECT_STORAGE_GCS_BUCKET")
        or ""
    ).strip()
    if not bucket:
        raise RuntimeError("ADK_ARTIFACT_BUCKET is required when ARTIFACT_BACKEND=gcs")
    return bucket


def get_artifact_service() -> ArtifactService:
    """Return a process singleton for the selected artifact backend."""
    global _service_singleton, _service_signature
    backend = artifact_backend_name()
    config = _local_root() if backend == "local" else _gcs_bucket() if backend == "gcs" else "memory"
    signature = (backend, config)
    if _service_singleton is not None and _service_signature == signature:
        return _service_singleton

    if backend == "local":
        _service_singleton = FileArtifactService(root_dir=config)
    elif backend == "gcs":
        _service_singleton = GcsArtifactService(bucket_name=config)
    else:
        _service_singleton = InMemoryArtifactService()
    _service_signature = signature
    return _service_singleton


def get_artifact_service_uri() -> str | None:
    """Return the URI understood by ADK's FastAPI service registry."""
    backend = artifact_backend_name()
    if backend == "local":
        return Path(_local_root()).expanduser().resolve().as_uri()
    if backend == "gcs":
        return f"gs://{_gcs_bucket()}"
    return None


def _reset_artifact_service_for_tests() -> None:
    global _service_singleton, _service_signature
    _service_singleton = None
    _service_signature = None
