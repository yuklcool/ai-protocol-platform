from __future__ import annotations

import pytest

from db.firestore_inmemory import InMemoryFirestoreClient
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository


@pytest.fixture(autouse=True)
def repository():
    # The backend-wide conftest intentionally replaces db.firestore._client with
    # a non-persistent MagicMock to catch accidental Firestore network access.
    # MemoryRepository normally reuses that client in LOCAL_MODE, so construct a
    # dedicated real in-memory client explicitly for repository contract tests.
    repo = MemoryRepository(client=InMemoryFirestoreClient())
    reset_repository_for_testing(repo)
    yield repo
    reset_repository_for_testing(None)


def test_default_folder_is_created_and_reused(repository: MemoryRepository) -> None:
    from db import folders

    folder_id = folders.ensure_default_folder("user-a")
    assert folders.ensure_default_folder("user-a") == folder_id

    stored = repository.get_document("document_folders", folder_id)
    assert stored is not None
    assert stored["userId"] == "user-a"
    assert stored["docCount"] == 0


def test_folder_listing_is_user_scoped(repository: MemoryRepository) -> None:
    from db import folders

    first = folders.create_folder("user-a", "A")
    folders.create_folder("user-b", "B")

    listed = folders.list_folders("user-a")
    assert [item["id"] for item in listed] == [first["id"]]


def test_folder_documents_come_from_canonical_parsed_documents(repository: MemoryRepository) -> None:
    from db import folders

    folder = folders.create_folder("user-a", "A")
    repository.set_document(
        "parsed_documents",
        "doc-a",
        {"userId": "user-a", "folderId": folder["id"], "createdAt": "2026-09-14T00:00:00+00:00"},
    )
    repository.set_document(
        "parsed_documents",
        "doc-b",
        {"userId": "user-b", "folderId": folder["id"], "createdAt": "2026-09-14T00:01:00+00:00"},
    )

    docs = folders.list_folder_documents("user-a", folder["id"])
    assert len(docs) == 1
    assert docs[0]["__id"] == "doc-a"


def test_folder_counts_use_repository_atomic_increment(repository: MemoryRepository) -> None:
    from db import folders

    folder = folders.create_folder("user-a", "A")
    folders.update_folder_counts("user-a", folder["id"], doc_delta=2, parsed_delta=1)
    folders.update_folder_counts("user-a", folder["id"], doc_delta=-1, parsed_delta=-1)

    stored = repository.get_document("document_folders", folder["id"])
    assert stored is not None
    assert stored["docCount"] == 1
    assert stored["parsedCount"] == 0


def test_get_folder_does_not_cross_users(repository: MemoryRepository) -> None:
    from db import folders

    folder = folders.create_folder("user-a", "A")
    assert folders.get_folder("user-a", folder["id"]) is not None
    assert folders.get_folder("user-b", folder["id"]) is None
