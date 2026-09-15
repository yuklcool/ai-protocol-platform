from __future__ import annotations

from pathlib import Path

import pytest
from google.genai import types

from adk import artifact_backend
from adk import session as session_mod
from adk.tenant_artifact_service import TenantScopedArtifactService
from auth import User
from observability.tenant_context import (
    clear_tenant_enrichers,
    get_current_tenant_id,
    register_tenant_enricher,
    set_tenant_context,
)


def _bind(tenant_id: str) -> None:
    set_tenant_context(
        User(
            uid="user-a",
            email="user-a@example.com",
            domain="example.com",
            tenant_id=tenant_id,
        )
    )


@pytest.fixture(autouse=True)
def _reset():
    artifact_backend._reset_artifact_service_for_tests()
    session_mod._reset_artifact_service_for_tests()
    clear_tenant_enrichers()
    _bind("tenant-test")
    yield
    clear_tenant_enrichers()
    session_mod._reset_artifact_service_for_tests()
    artifact_backend._reset_artifact_service_for_tests()


def test_enricher_cannot_override_verified_tenant_identity() -> None:
    register_tenant_enricher(lambda _user: {"tenant.id": "legacy-domain", "trace.cohort": "blue"})
    set_tenant_context(
        User(
            uid="user-a",
            email="user-a@example.com",
            domain="legacy-domain",
            tenant_id="tenant-explicit",
        ),
        extra={"tenant.id": "request-spoof", "trace.request": "yes"},
    )
    assert get_current_tenant_id() == "tenant-explicit"


@pytest.mark.asyncio
async def test_local_artifact_survives_service_reconstruction(tmp_path: Path, monkeypatch):
    root = tmp_path / "artifacts"
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(root))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.delenv("ADK_ARTIFACT_BUCKET", raising=False)

    _bind("tenant-a")
    first = artifact_backend.get_artifact_service()
    version = await first.save_artifact(
        app_name="aitana_platform",
        user_id="user-a",
        session_id="session-a",
        filename="report.txt",
        artifact=types.Part.from_text(text="persistent artifact"),
    )
    assert version == 0

    artifact_backend._reset_artifact_service_for_tests()
    _bind("tenant-a")
    second = artifact_backend.get_artifact_service()
    restored = await second.load_artifact(
        app_name="aitana_platform",
        user_id="user-a",
        session_id="session-a",
        filename="report.txt",
    )

    assert restored is not None
    assert restored.text == "persistent artifact"
    assert await second.list_versions(
        app_name="aitana_platform",
        user_id="user-a",
        session_id="session-a",
        filename="report.txt",
    ) == [0]


@pytest.mark.asyncio
async def test_same_uid_cannot_read_artifact_from_another_tenant(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)

    service = artifact_backend.get_artifact_service()

    _bind("tenant-a")
    await service.save_artifact(
        app_name="aitana_platform",
        user_id="same-uid",
        session_id="same-session",
        filename="secret.txt",
        artifact=types.Part.from_text(text="tenant-a only"),
    )

    _bind("tenant-b")
    foreign = await service.load_artifact(
        app_name="aitana_platform",
        user_id="same-uid",
        session_id="same-session",
        filename="secret.txt",
    )
    assert foreign is None
    assert await service.list_artifact_keys(
        app_name="aitana_platform",
        user_id="same-uid",
        session_id="same-session",
    ) == []


@pytest.mark.asyncio
async def test_artifact_access_without_tenant_context_fails_closed(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)

    service = TenantScopedArtifactService(
        artifact_backend._build_delegate("local", str(tmp_path / "artifacts-direct")),
        tenant_resolver=lambda: "",
    )
    with pytest.raises(PermissionError, match="stable tenant context"):
        await service.list_artifact_keys(
            app_name="aitana_platform",
            user_id="user-a",
            session_id="session-a",
        )


def test_selfhost_object_backend_selects_tenant_scoped_file_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)

    service = artifact_backend.get_artifact_service()
    assert isinstance(service, TenantScopedArtifactService)
    assert type(service.delegate).__name__ == "FileArtifactService"
    assert artifact_backend.get_artifact_service_uri().startswith("file://")


def test_session_facade_uses_same_tenant_scoped_local_artifact_backend(tmp_path: Path, monkeypatch):
    """Production AG-UI/FastAPI callers import artifacts through adk.session."""
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "runtime-artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.delenv("ADK_ARTIFACT_BUCKET", raising=False)

    service = session_mod.get_artifact_service()
    assert isinstance(service, TenantScopedArtifactService)
    assert type(service.delegate).__name__ == "FileArtifactService"
    assert session_mod.get_artifact_service_uri().startswith("file://")
    assert service is artifact_backend.get_artifact_service()


def test_existing_gcs_bucket_keeps_cloud_default(monkeypatch):
    monkeypatch.delenv("OBJECT_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.setenv("ADK_ARTIFACT_BUCKET", "existing-cloud-bucket")

    assert artifact_backend.artifact_backend_name() == "gcs"
    assert artifact_backend.get_artifact_service_uri() == "gs://existing-cloud-bucket"


def test_explicit_memory_remains_available_behind_tenant_boundary(monkeypatch):
    monkeypatch.setenv("ARTIFACT_BACKEND", "memory")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

    service = artifact_backend.get_artifact_service()
    assert isinstance(service, TenantScopedArtifactService)
    assert type(service.delegate).__name__ == "InMemoryArtifactService"
    assert artifact_backend.get_artifact_service_uri() is None
