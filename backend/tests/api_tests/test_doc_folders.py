"""API tests for document-folder CRUD and authenticated document access."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user

_USER_A = User(uid="user_a", email="alice@example.com", domain="example.com")
_USER_B = User(uid="user_b", email="bob@example.com", domain="example.com")


@pytest.fixture()
def app_a() -> TestClient:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _USER_A
    return TestClient(app)


@pytest.fixture()
def app_b() -> TestClient:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _USER_B
    return TestClient(app)


@pytest.fixture()
def app_anon() -> TestClient:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestPostFolders:
    def test_create_folder_returns_201(self, app_a: TestClient):
        with patch("db.folders.create_folder") as mock_create:
            mock_create.return_value = {
                "id": "folder1",
                "name": "Q1 Review",
                "userId": "user_a",
                "tenantId": "example.com",
                "docCount": 0,
                "parsedCount": 0,
            }
            resp = app_a.post("/api/folders", json={"name": "Q1 Review"})
        assert resp.status_code == 201
        assert resp.json()["id"] == "folder1"
        mock_create.assert_called_once_with(user_id="user_a", name="Q1 Review", tenant_id="example.com")

    def test_create_folder_passes_uid_and_tenant(self, app_a: TestClient):
        calls = []

        def capturing_create(user_id: str, name: str, *, tenant_id: str | None = None) -> dict:
            calls.append((user_id, name, tenant_id))
            return {
                "id": "f1",
                "name": name,
                "userId": user_id,
                "tenantId": tenant_id or "",
                "docCount": 0,
                "parsedCount": 0,
            }

        with patch("db.folders.create_folder", side_effect=capturing_create):
            app_a.post("/api/folders", json={"name": "My Folder"})
        assert calls == [("user_a", "My Folder", "example.com")]

    def test_requires_auth(self, app_anon: TestClient):
        assert app_anon.post("/api/folders", json={"name": "test"}).status_code == 401


class TestGetFolders:
    def test_returns_caller_folders_only(self, app_a: TestClient):
        folders = [{"id": "f1", "name": "My Docs", "userId": "user_a", "docCount": 3, "parsedCount": 3}]
        with patch("db.folders.list_folders", return_value=folders) as mock_list:
            resp = app_a.get("/api/folders")
        assert resp.status_code == 200
        assert resp.json()["folders"][0]["id"] == "f1"
        mock_list.assert_called_once_with(user_id="user_a", tenant_id="example.com")


class TestGetFolderDocuments:
    def test_returns_documents_for_own_folder(self, app_a: TestClient):
        docs = [{"id": "doc1", "title": "Report.docx", "parseStatus": "parsed", "blockCount": 42}]
        with (
            patch("db.folders.get_folder", return_value={"id": "f1", "userId": "user_a"}) as mock_get,
            patch("db.folders.list_folder_documents", return_value=docs) as mock_docs,
        ):
            resp = app_a.get("/api/folders/f1/documents")
        assert resp.status_code == 200
        assert resp.json()["documents"][0]["parseStatus"] == "parsed"
        mock_get.assert_called_once_with(user_id="user_a", folder_id="f1", tenant_id="example.com")
        mock_docs.assert_called_once_with(user_id="user_a", folder_id="f1", tenant_id="example.com")

    def test_other_users_folder_is_403(self, app_a: TestClient):
        with patch("db.folders.get_folder", return_value={"id": "f1", "userId": "user_b"}):
            assert app_a.get("/api/folders/f1/documents").status_code == 403


_PARSED_DOC = {
    "id": "doc123",
    "userId": "user_a",
    "tenantId": "example.com",
    "originalFilename": "report.docx",
    "sourceFormat": "docx",
    "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "parseStatus": "parsed",
    "storageBackend": "local",
    "storagePath": "users/user_a/docs/f/report.docx",
    "summary": {"totalBlocks": 10},
    "a2uiComponents": {"root": "root-1", "components": []},
}


class TestGetDocument:
    def test_returns_document_for_owner(self, app_a: TestClient):
        with patch("tools.documents.routes._get_document_record", return_value=dict(_PARSED_DOC)):
            resp = app_a.get("/api/documents/doc123")
        assert resp.status_code == 200
        assert resp.json()["id"] == "doc123"

    def test_missing_is_404(self, app_a: TestClient):
        with patch("tools.documents.routes._get_document_record", return_value=None):
            assert app_a.get("/api/documents/missing").status_code == 404

    def test_other_user_is_403(self, app_b: TestClient):
        with patch("tools.documents.routes._get_document_record", return_value=dict(_PARSED_DOC)):
            assert app_b.get("/api/documents/doc123").status_code == 403


_UNICODE_DOC = {
    **_PARSED_DOC,
    "id": "docU",
    "originalFilename": "Din SAS-booking bekræftet, 1 Jul – 8 Jul.pdf",
    "sourceFormat": "pdf",
    "contentType": "application/pdf",
    "storagePath": "users/user_a/docs/f/booking.pdf",
}


def _storage(data: bytes) -> MagicMock:
    storage = MagicMock()
    storage.exists.return_value = True
    storage.iter_bytes.return_value = iter([data[:5], data[5:]])
    storage.get_bytes.return_value = data
    return storage


class TestPreviewAndDownload:
    def test_unicode_filename_previews_without_500(self, app_a: TestClient):
        storage = _storage(b"%PDF-1.4 fake")
        with (
            patch("tools.documents.routes._get_document_record", return_value=dict(_UNICODE_DOC)),
            patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", _UNICODE_DOC["storagePath"], "local")),
        ):
            resp = app_a.get("/api/documents/docU/preview")
        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 fake"
        cd = resp.headers["content-disposition"]
        cd.encode("latin-1")
        assert "filename*=UTF-8''" in cd
        assert "%E2%80%93" in cd

    def test_download_is_attachment(self, app_a: TestClient):
        storage = _storage(b"download-me")
        with (
            patch("tools.documents.routes._get_document_record", return_value=dict(_PARSED_DOC)),
            patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", _PARSED_DOC["storagePath"], "local")),
        ):
            resp = app_a.get("/api/documents/doc123/download")
        assert resp.status_code == 200
        assert resp.content == b"download-me"
        assert resp.headers["content-disposition"].startswith("attachment;")

    def test_other_users_doc_is_403_before_storage(self, app_b: TestClient):
        with patch("tools.documents.routes._get_document_record", return_value=dict(_UNICODE_DOC)):
            assert app_b.get("/api/documents/docU/preview").status_code == 403

    def test_cross_tenant_metadata_is_403(self, app_a: TestClient):
        doc = {**_PARSED_DOC, "tenantId": "other.example"}
        with patch("tools.documents.routes._get_document_record", return_value=doc):
            assert app_a.get("/api/documents/doc123/download").status_code == 403
