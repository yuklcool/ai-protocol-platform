"""Tests for provider-neutral document thumbnail rendering."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user

_USER_A = User(uid="user_a", email="alice@example.com", domain="example.com")
_USER_B = User(uid="user_b", email="bob@example.com", domain="example.com")

_DOC = {
    "id": "doc_1",
    "userId": "user_a",
    "tenantId": "example.com",
    "originalFilename": "sample.pdf",
    "sourceFormat": "pdf",
    "storageBackend": "local",
    "storagePath": "users/user_a/docs/f/sample.pdf",
    "parseStatus": "parsed",
}


def _app_for(user: User) -> TestClient:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _one_page_pdf() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (420, 594), "white").save(buf, "PDF")
    return buf.getvalue()


def _png_image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(buf, "PNG")
    return buf.getvalue()


def _storage(data: bytes) -> MagicMock:
    storage = MagicMock()
    storage.get_bytes.return_value = data
    return storage


def test_thumbnail_anon_401() -> None:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/api/documents/doc_1/thumbnail").status_code == 401


def test_thumbnail_owner_renders_png() -> None:
    client = _app_for(_USER_A)
    storage = _storage(_one_page_pdf())
    with (
        patch("tools.documents.routes._get_document_record", return_value=dict(_DOC)),
        patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", _DOC["storagePath"], "local")),
    ):
        resp = client.get("/api/documents/doc_1/thumbnail?width=300")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumbnail_image_doc_renders_png() -> None:
    client = _app_for(_USER_A)
    doc = {**_DOC, "sourceFormat": "png", "originalFilename": "logo.png", "storagePath": "users/user_a/docs/f/logo.png"}
    storage = _storage(_png_image())
    with (
        patch("tools.documents.routes._get_document_record", return_value=doc),
        patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", doc["storagePath"], "local")),
    ):
        resp = client.get("/api/documents/doc_1/thumbnail?width=200")
    assert resp.status_code == 200
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumbnail_non_owner_403() -> None:
    client = _app_for(_USER_B)
    with patch("tools.documents.routes._get_document_record", return_value=dict(_DOC)):
        assert client.get("/api/documents/doc_1/thumbnail").status_code == 403


def test_thumbnail_missing_doc_404() -> None:
    client = _app_for(_USER_A)
    with patch("tools.documents.routes._get_document_record", return_value=None):
        assert client.get("/api/documents/missing/thumbnail").status_code == 404


def test_thumbnail_unsupported_format_415() -> None:
    client = _app_for(_USER_A)
    doc = {**_DOC, "sourceFormat": "txt", "originalFilename": "notes.txt"}
    with patch("tools.documents.routes._get_document_record", return_value=doc):
        assert client.get("/api/documents/doc_1/thumbnail").status_code == 415
