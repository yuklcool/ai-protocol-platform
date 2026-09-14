from __future__ import annotations

import os
import uuid

import pytest

from db.persistence import get_repository, reset_repository_for_testing


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration test")
    return value


def test_folder_document_and_agent_context_share_postgres(monkeypatch) -> None:
    database_url = _database_url()
    suffix = uuid.uuid4().hex[:12]
    user_id = f"doc-user-{suffix}"
    doc_id = f"doc-{suffix}"

    monkeypatch.setenv("DATA_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_repository_for_testing(None)

    from db import folders
    from tools.documents.context import build_document_context

    folder = folders.create_folder(user_id, "Integration")
    folder_id = folder["id"]
    repo = get_repository()
    repo.set_document(
        "parsed_documents",
        doc_id,
        {
            "userId": user_id,
            "tenantId": "example.com",
            "folderId": folder_id,
            "originalFilename": "integration.txt",
            "sourceFormat": "txt",
            "parseStatus": "parsed",
            "status": "parsed",
            "blocks": [{"type": "paragraph", "text": f"postgres-content-{suffix}"}],
            "editedBlocks": {},
            "createdAt": "2026-09-14T03:00:00+00:00",
            "updatedAt": "2026-09-14T03:00:00+00:00",
        },
    )

    folders.update_folder_counts(user_id, folder_id, doc_delta=1, parsed_delta=1)
    listed = folders.list_folder_documents(user_id, folder_id)
    assert [item["__id"] for item in listed] == [doc_id]

    stored_folder = folders.get_folder(user_id, folder_id)
    assert stored_folder is not None
    assert stored_folder["docCount"] == 1
    assert stored_folder["parsedCount"] == 1

    context, blocks = build_document_context(doc_id)
    assert f"postgres-content-{suffix}" in context
    assert blocks is None

    repo.delete_document("parsed_documents", doc_id)
    repo.delete_document("document_folders", folder_id)
    reset_repository_for_testing(None)
