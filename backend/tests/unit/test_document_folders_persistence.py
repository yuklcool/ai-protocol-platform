"""Folder queries and mutations use verified user ownership."""

import pytest

from auth.models import User
from db import folders
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from observability.user_context import set_user_context


@pytest.fixture
def repository():
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    set_user_context(User(uid="alice"))
    return repo


def test_default_folder_is_created_and_reused(repository):
    ref = folders.ensure_default_folder("alice")
    assert folders.ensure_default_folder("alice") == ref
    assert repository.get_document("document_folders", ref)["userId"] == "alice"


def test_folder_listing_is_user_owned(repository):
    first = folders.create_folder("alice", "A")
    set_user_context(User(uid="bob"))
    folders.create_folder("bob", "B")
    set_user_context(User(uid="alice"))
    assert [row["id"] for row in folders.list_folders("alice")] == [first["id"]]
    with pytest.raises(PermissionError):
        folders.list_folders("bob")


def test_folder_documents_come_from_canonical_owned_documents(repository):
    folder = folders.create_folder("alice", "A")
    for ref, owner in (("a", "alice"), ("b", "bob")):
        repository.set_document("parsed_documents", ref, {"userId": owner, "folderId": folder["id"]})
    assert [row["__id"] for row in folders.list_folder_documents("alice", folder["id"])] == ["a"]


def test_folder_counts_use_repository_atomic_increment(repository):
    folder = folders.create_folder("alice", "A")
    folders.update_folder_counts("alice", folder["id"], doc_delta=2, parsed_delta=1)
    folders.update_folder_counts("alice", folder["id"], doc_delta=-1, parsed_delta=-1)
    row = repository.get_document("document_folders", folder["id"])
    assert (row["docCount"], row["parsedCount"]) == (1, 0)


def test_folder_is_unavailable_to_another_user(repository):
    folder = folders.create_folder("alice", "A")
    set_user_context(User(uid="bob"))
    assert folders.get_folder("bob", folder["id"]) is None
    with pytest.raises(PermissionError):
        folders.get_folder("alice", folder["id"])
