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

    from auth import User
    from db import folders
    from observability.user_context import set_user_context
    from tools.documents.context import build_document_context

    set_user_context(User(uid=user_id))
    folder = folders.create_folder(user_id, "Integration")
    folder_id = folder["id"]
    repo = get_repository()
    repo.set_document(
        "parsed_documents",
        doc_id,
        {
            "userId": user_id,
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

    from auth import User
    from observability.user_context import set_user_context

    set_user_context(User(uid=user_id, email="postgres@example.com"))
    context, blocks = build_document_context(doc_id)
    assert f"postgres-content-{suffix}" in context
    assert blocks is None

    repo.delete_document("parsed_documents", doc_id)
    repo.delete_document("document_folders", folder_id)
    reset_repository_for_testing(None)


def test_session_attachment_choices_survive_repository_restart_and_user_switch(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from auth import User, build_access_context
    from db.chat_sessions import create_session_index, get_session_index, set_session_documents
    from db.models.access import AccessControl
    from observability.user_context import _context, set_user_context
    from protocols.session_document_routes import DocumentSelection, get_documents, save_documents
    from tools.documents.access import DocumentUnavailable, readable_document

    monkeypatch.setenv("DATABASE_URL", _database_url())
    monkeypatch.setenv("DATA_BACKEND", "postgres")
    reset_repository_for_testing(None)
    suffix = uuid.uuid4().hex[:12]
    session_id, doc_id, other_id = (f"{prefix}-{suffix}" for prefix in ("session", "doc", "other"))
    owner = User(uid=f"owner-{suffix}", email="owner@example.com")
    other = owner.model_copy(update={"uid": f"other-user-{suffix}"})
    token = _context.set(None)
    set_user_context(owner)
    request = SimpleNamespace(state=SimpleNamespace(access=build_access_context(owner)))
    repo = get_repository()
    try:
        for key in (doc_id, other_id):
            repo.set_document(
                "parsed_documents",
                key,
                {
                    "userId": owner.uid,
                    "originalFilename": f"{key}.txt",
                    "sourceFormat": "txt",
                    "parseStatus": "parsed",
                    "blocks": [{"type": "paragraph", "text": f"persisted-{key}"}],
                },
            )
        create_session_index(
            session_id=session_id,
            skill_id="root-agent",
            owner_uid=owner.uid,
            access_control=AccessControl(type="private"),
            owner_domain="example.com",
            agent_id="root-agent",
        )
        selected = DocumentSelection(documents=[{"id": doc_id, "included": True}, {"id": other_id, "included": False}])
        save_documents(session_id, selected, request, owner)
        set_session_documents(session_id, [other_id])
        reset_repository_for_testing(None)
        restored = get_documents(session_id, request, owner)["documents"]
        assert [(row["id"], row["included"]) for row in restored] == [(doc_id, False), (other_id, True)]
        assert readable_document(other_id, user_id=owner.uid)["blocks"][0]["text"] == f"persisted-{other_id}"
        set_session_documents(session_id, [])
        reset_repository_for_testing(None)
        assert get_session_index(session_id).document_ids == []
        assert not any(row["included"] for row in get_documents(session_id, request, owner)["documents"])
        set_user_context(other)
        with pytest.raises(DocumentUnavailable):
            readable_document(other_id, user_id=other.uid)
        with pytest.raises(HTTPException) as denied:
            get_documents(session_id, SimpleNamespace(state=SimpleNamespace(access=build_access_context(other))), other)
        assert denied.value.status_code == 403
    finally:
        set_user_context(owner)
        for collection, key in [
            ("chat_sessions", session_id),
            ("parsed_documents", doc_id),
            ("parsed_documents", other_id),
        ]:
            get_repository().delete_document(collection, key)
        reset_repository_for_testing(None)
        _context.reset(token)
