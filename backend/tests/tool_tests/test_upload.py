"""Tests for tools/documents/upload.py."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user

_USER = User(uid="user123", email="test@example.com", domain="example.com")


# --- Plain-text parse path (v6.14.0): .txt no longer strands on "Parsing…" ---


@pytest.mark.asyncio
async def test_run_parse_txt_emits_paragraph_blocks_and_parsed_status():
    from tools.documents.upload import _run_parse

    text = b"First paragraph.\n\nSecond paragraph.\n\nThird."
    blob = MagicMock()
    blob.download_as_bytes.return_value = text
    client = MagicMock()
    client.bucket.return_value.blob.return_value = blob
    with patch("google.cloud.storage.Client", return_value=client):
        status, blocks, _ms, err = await _run_parse("gs://bucket/users/u/docs/notes.txt")

    assert status == "parsed" and err is None
    assert [b["text"] for b in blocks] == ["First paragraph.", "Second paragraph.", "Third."]
    assert all(b["type"] == "paragraph" and b.get("block_id") for b in blocks)


@pytest.mark.asyncio
async def test_run_parse_txt_read_failure_is_failed_not_stranded():
    from tools.documents.upload import _run_parse

    with patch("google.cloud.storage.Client", side_effect=RuntimeError("no creds")):
        status, blocks, _ms, err = await _run_parse("gs://bucket/x.txt")
    # A read failure is a clear terminal state — NEVER the never-resolving
    # pending_ai_extraction that stranded the viewer.
    assert status == "failed" and blocks == [] and err


@pytest.fixture
def upload_client(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "gcs")
    from tools.documents.upload import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    return TestClient(app)


def _file(name: str = "report.docx") -> dict:
    return {"file": (name, io.BytesIO(b"fake content"), "application/octet-stream")}


def _common_patches(parse_return=("parsed", [{"type": "paragraph", "text": "Hi"}], 10, None)):
    return [
        patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
        patch(
            "tools.documents.upload.GcsObjectStorage.put_fileobj",
            return_value=SimpleNamespace(uri="gs://test-bucket/object"),
        ),
        patch("tools.documents.upload._run_parse_fileobj", return_value=parse_return),
        patch("tools.documents.upload.set_document"),
        patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="folder1"),
        patch("tools.documents.upload.folders_db.update_folder_counts"),
    ]


class TestUploadEndpoint:
    def test_unsupported_extension(self, upload_client):
        resp = upload_client.post(
            "/api/documents/upload",
            files={"file": ("script.exe", io.BytesIO(b"binary"), "application/octet-stream")},
        )
        assert resp.status_code == 415
        assert "暂不支持" in resp.json()["detail"]

    def test_docx_upload_success(self, upload_client):
        fake_blocks = [{"type": "paragraph", "text": "Hello"}]
        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
            patch(
                "tools.documents.upload.GcsObjectStorage.put_fileobj",
                return_value=SimpleNamespace(uri="gs://test-bucket/object"),
            ),
            patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", fake_blocks, 11, None)),
            patch("tools.documents.upload.set_document") as mock_set,
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="folder1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            resp = upload_client.post("/api/documents/upload", files=_file(), data={"skill_id": "my-skill"})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "parsed"
        assert data["originalFilename"] == "report.docx"
        assert data["blocksCount"] == 1
        assert data["folderId"] == "folder1"
        mock_set.assert_called()

    def test_blocks_stored_in_firestore_on_success(self, upload_client):
        """Regression: blocks must be persisted to Firestore so build_document_context can load them."""
        fake_blocks = [{"type": "heading", "text": "Intro"}, {"type": "paragraph", "text": "Body"}]
        stored: dict = {}

        def capture_set(collection, doc_id, doc, **kwargs):
            stored.update(doc)

        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
            patch(
                "tools.documents.upload.GcsObjectStorage.put_fileobj",
                return_value=SimpleNamespace(uri="gs://test-bucket/object"),
            ),
            patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", fake_blocks, 20, None)),
            patch("tools.documents.upload.set_document", side_effect=capture_set),
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="f1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            upload_client.post("/api/documents/upload", files=_file())

        assert "blocks" in stored, "blocks field missing from Firestore document"
        assert stored["blocks"] == fake_blocks, "blocks content mismatch"

    def test_failed_parse_stores_empty_blocks(self, upload_client):
        """Failed parse should store [] not the parsed blocks (there are none)."""
        stored: dict = {}

        def capture_set(collection, doc_id, doc, **kwargs):
            stored.update(doc)

        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
            patch(
                "tools.documents.upload.GcsObjectStorage.put_fileobj",
                return_value=SimpleNamespace(uri="gs://test-bucket/object"),
            ),
            patch("tools.documents.upload._run_parse_fileobj", return_value=("failed", [], 5, "timeout")),
            patch("tools.documents.upload.set_document", side_effect=capture_set),
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="f1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            upload_client.post("/api/documents/upload", files=_file())

        assert stored.get("blocks") == []
        assert stored.get("parseStatus") == "failed"

    def test_ailang_parse_failure_returns_failed_status(self, upload_client):
        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
            patch(
                "tools.documents.upload.GcsObjectStorage.put_fileobj",
                return_value=SimpleNamespace(uri="gs://test-bucket/object"),
            ),
            patch("tools.documents.upload._run_parse_fileobj", return_value=("failed", [], 5, "parse error")),
            patch("tools.documents.upload.set_document"),
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="folder1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            resp = upload_client.post("/api/documents/upload", files=_file())

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_corrupt_pdf_returns_terminal_failed_status(self, upload_client):
        """When AILANG can't parse a format at all, the upload returns the
        pending_ai_extraction status so the frontend / agent can surface the
        in-progress state. PDFs USED to take this path because PDF was excluded
        from the original DETERMINISTIC_EXTENSIONS gate — but as of 2026-06-11
        PDFs (and images) are in PARSEABLE_EXTENSIONS, so they hit the real
        parse path. Force the gate closed here to exercise the legacy fallback.
        """
        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="test-bucket"),
            patch(
                "tools.documents.upload.GcsObjectStorage.put_fileobj",
                return_value=SimpleNamespace(uri="gs://test-bucket/object"),
            ),
            patch("tools.documents.ailang_parse.is_parseable", return_value=False),
            patch("tools.documents.upload.set_document"),
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="folder1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            resp = upload_client.post(
                "/api/documents/upload",
                files={"file": ("document.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_bucket_comes_from_resolve_documents_bucket(self, upload_client):
        with (
            patch("tools.documents.upload.resolve_documents_bucket", return_value="client-specific-bucket"),
            patch("tools.documents.upload.GcsObjectStorage") as storage,
            patch("tools.documents.upload._run_parse_fileobj", return_value=("parsed", [], 0, None)),
            patch("tools.documents.upload.set_document"),
            patch("tools.documents.upload.folders_db.ensure_default_folder", return_value="f1"),
            patch("tools.documents.upload.folders_db.update_folder_counts"),
        ):
            storage.return_value.put_fileobj.return_value = SimpleNamespace(uri="gs://client-specific-bucket/object")
            response = upload_client.post("/api/documents/upload", files=_file())
        assert response.status_code == 200
        storage.assert_called_once_with("client-specific-bucket")

    def test_same_filename_creates_independent_resources(self, upload_client):
        from contextlib import ExitStack

        patches = _common_patches()
        with ExitStack() as stack:
            mocks = [stack.enter_context(item) for item in patches]
            first = upload_client.post("/api/documents/upload", files=_file()).json()
            second = upload_client.post("/api/documents/upload", files=_file()).json()
        assert first["docId"] != second["docId"]
        assert first["storagePath"] != second["storagePath"]
        assert first["docId"] in first["storagePath"]
        assert second["docId"] in second["storagePath"]
        assert mocks[-1].call_count == 2
        assert all(call.kwargs["doc_delta"] == 1 for call in mocks[-1].call_args_list)
