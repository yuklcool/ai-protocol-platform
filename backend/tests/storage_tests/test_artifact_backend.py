from __future__ import annotations

from pathlib import Path

import pytest
from google.genai import types

from adk import artifact_backend
from adk import session as session_mod


@pytest.fixture(autouse=True)
def _reset():
    artifact_backend._reset_artifact_service_for_tests()
    session_mod._reset_artifact_service_for_tests()
    yield
    session_mod._reset_artifact_service_for_tests()
    artifact_backend._reset_artifact_service_for_tests()


@pytest.mark.asyncio
async def test_local_artifact_survives_service_reconstruction(tmp_path: Path, monkeypatch):
    root = tmp_path / "artifacts"
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(root))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.delenv("ADK_ARTIFACT_BUCKET", raising=False)

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


def test_selfhost_object_backend_selects_file_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)

    service = artifact_backend.get_artifact_service()
    assert type(service).__name__ == "FileArtifactService"
    assert artifact_backend.get_artifact_service_uri().startswith("file://")


def test_session_facade_uses_same_local_artifact_backend(tmp_path: Path, monkeypatch):
    """Production AG-UI/FastAPI callers import artifacts through adk.session."""
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADK_ARTIFACT_ROOT", str(tmp_path / "runtime-artifacts"))
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.delenv("ADK_ARTIFACT_BUCKET", raising=False)

    service = session_mod.get_artifact_service()
    assert type(service).__name__ == "FileArtifactService"
    assert session_mod.get_artifact_service_uri().startswith("file://")
    assert service is artifact_backend.get_artifact_service()


def test_existing_gcs_bucket_keeps_cloud_default(monkeypatch):
    monkeypatch.delenv("OBJECT_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("ARTIFACT_BACKEND", raising=False)
    monkeypatch.setenv("ADK_ARTIFACT_BUCKET", "existing-cloud-bucket")

    assert artifact_backend.artifact_backend_name() == "gcs"
    assert artifact_backend.get_artifact_service_uri() == "gs://existing-cloud-bucket"


def test_explicit_memory_remains_available(monkeypatch):
    monkeypatch.setenv("ARTIFACT_BACKEND", "memory")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

    service = artifact_backend.get_artifact_service()
    assert type(service).__name__ == "InMemoryArtifactService"
    assert artifact_backend.get_artifact_service_uri() is None
