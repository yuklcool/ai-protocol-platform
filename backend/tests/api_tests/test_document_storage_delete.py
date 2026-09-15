from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user

USER = User(uid="user_a", email="alice@example.com", domain="example.com")
DOC = {
    "id": "doc1",
    "userId": "user_a",
    "tenantId": "example.com",
    "originalFilename": "report.txt",
    "sourceFormat": "txt",
    "storageBackend": "local",
    "storagePath": "users/user_a/docs/f1/report.txt",
    "parseStatus": "parsed",
    "folderId": "f1",
}


def client() -> TestClient:
    from tools.documents.routes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app)


def test_delete_removes_binary_then_metadata() -> None:
    storage = MagicMock()
    with (
        patch("tools.documents.routes._get_document_record", return_value=dict(DOC)),
        patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", DOC["storagePath"], "local")),
        patch("tools.documents.routes._set_document_record") as mark,
        patch("tools.documents.routes._delete_document_record") as delete_record,
        patch("db.folders.update_folder_counts") as counts,
    ):
        response = client().delete("/api/documents/doc1")

    assert response.status_code == 204
    storage.delete.assert_called_once_with("example.com", DOC["storagePath"])
    delete_record.assert_called_once_with("parsed_documents", "doc1")
    assert mark.call_args_list[0].args[2]["deletionStatus"] == "deleting"
    counts.assert_called_once_with(
        "user_a",
        "f1",
        doc_delta=-1,
        parsed_delta=-1,
        tenant_id="example.com",
    )


def test_delete_storage_failure_preserves_metadata() -> None:
    storage = MagicMock()
    storage.delete.side_effect = OSError("storage unavailable")
    with (
        patch("tools.documents.routes._get_document_record", return_value=dict(DOC)),
        patch("tools.documents.routes._storage_binding", return_value=(storage, "example.com", DOC["storagePath"], "local")),
        patch("tools.documents.routes._set_document_record") as mark,
        patch("tools.documents.routes._delete_document_record") as delete_record,
    ):
        response = client().delete("/api/documents/doc1")

    assert response.status_code == 502
    delete_record.assert_not_called()
    assert [call.args[2].get("deletionStatus") for call in mark.call_args_list] == ["deleting", "failed"]
