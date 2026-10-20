"""Tests for POST /api/documents/upload — streaming ObjectStorage + folder metadata."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user
from object_storage.factory import _reset_object_storage_for_tests
from tests.support.identity import identity_dependency

_USER = User(uid="user1", email="alice@example.com", domain="example.com")


@pytest.fixture(autouse=True)
def _reset_storage():
    _reset_object_storage_for_tests()
    yield
    _reset_object_storage_for_tests()


@pytest.fixture()
def client() -> TestClient:
    from tools.documents.upload import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = identity_dependency(_USER)
    return TestClient(app)


def _file(name: str = "test.docx", data: bytes = b"fake content") -> dict:
    return {"file": (name, BytesIO(data), "application/octet-stream")}


def _common_patches():
    return (
        patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", [], 10, None)),
        patch("tools.documents.upload._store_document"),
        patch("db.folders.ensure_default_folder", return_value="folder1"),
        patch("db.folders.update_folder_counts"),
    )


class TestUploadStorage:
    def test_local_backend_streams_to_tenant_volume(self, client: TestClient, tmp_path: Path, monkeypatch):
        root = tmp_path / "objects"
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(root))
        common = _common_patches()
        with (
            common[0],
            common[1],
            common[2],
            common[3],
            patch("tools.documents.upload.resolve_documents_bucket") as bucket_resolver,
        ):
            resp = client.post("/api/documents/upload", files=_file())

        assert resp.status_code == 200
        bucket_resolver.assert_not_called()
        stored = root / "users" / "user1" / "users" / "user1" / "docs" / "folder1" / resp.json()["docId"] / "test.docx"
        assert stored.read_bytes() == b"fake content"

    def test_gcs_backend_uses_fileobj_and_per_client_bucket(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "gcs")
        captured = {}

        class FakeGcsStorage:
            def __init__(self, bucket_name: str):
                captured["bucket"] = bucket_name

            def put_fileobj(self, tenant_id: str, key: str, fileobj):
                captured["tenant"] = tenant_id
                captured["key"] = key
                captured["data"] = fileobj.read()
                return SimpleNamespace(uri=f"gs://{captured['bucket']}/{key}")

        common = _common_patches()
        with (
            common[0],
            common[1],
            common[2],
            common[3],
            patch("tools.documents.upload.resolve_documents_bucket", return_value="example-documents"),
            patch("tools.documents.upload.GcsObjectStorage", FakeGcsStorage),
        ):
            resp = client.post("/api/documents/upload", files=_file())

        assert resp.status_code == 200
        assert captured["bucket"] == "example-documents"
        assert captured["tenant"] == "user1"
        assert captured["key"].startswith("users/user1/docs/")
        assert captured["data"] == b"fake content"

    def test_storage_path_uses_uid_docs_folder_pattern(self, client: TestClient, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
        common = _common_patches()
        with common[0], common[1], common[2], common[3]:
            resp = client.post("/api/documents/upload", files=_file())
        assert resp.status_code == 200
        assert resp.json()["storagePath"].startswith(f"users/{_USER.uid}/docs/")

    def test_parse_status_pending_written_immediately(self, client: TestClient, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
        immediate_writes = []

        def fake_store(doc_id, *, parse_result, **kwargs):
            if parse_result.status == "pending":
                immediate_writes.append((doc_id, kwargs["user_id"], kwargs["storage_backend"]))

        with (
            patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", [], 10, None)),
            patch("tools.documents.upload._store_document", side_effect=fake_store),
            patch("db.folders.ensure_default_folder", return_value="folder1"),
            patch("db.folders.update_folder_counts"),
        ):
            client.post("/api/documents/upload", files=_file())

        assert len(immediate_writes) == 1
        assert immediate_writes[0][1:] == ("user1", "local")

    def test_auto_creates_folder_when_none_provided(self, client: TestClient, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
        calls = []

        def capture_ensure(uid: str, *, tenant_id: str | None = None) -> str:
            calls.append((uid, tenant_id))
            return "auto-folder"

        with (
            patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", [], 10, None)),
            patch("tools.documents.upload._store_document"),
            patch("db.folders.ensure_default_folder", side_effect=capture_ensure),
            patch("db.folders.update_folder_counts"),
        ):
            resp = client.post("/api/documents/upload", files=_file())

        assert resp.status_code == 200
        assert calls == [("user1", None)]

    def test_large_payload_reaches_storage_without_upload_route_reading_bytes(
        self, client: TestClient, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
        payload = b"x" * (3 * 1024 * 1024 + 17)
        common = _common_patches()
        with common[0], common[1], common[2], common[3]:
            resp = client.post("/api/documents/upload", files=_file(data=payload))

        assert resp.status_code == 200
        stored = (
            tmp_path
            / "objects"
            / "users"
            / "user1"
            / "users"
            / "user1"
            / "docs"
            / "folder1"
            / resp.json()["docId"]
            / "test.docx"
        )
        assert stored.stat().st_size == len(payload)

    def test_unsupported_extension_returns_415(self, client: TestClient):
        resp = client.post("/api/documents/upload", files=_file("test.exe"))
        assert resp.status_code == 415
