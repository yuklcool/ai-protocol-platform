from __future__ import annotations

import os

import pytest

from auth.group_id_auth import (
    AnonymousGroupAuth,
    GroupRevoked,
    create_group,
    delete_group,
    get_group,
    join_group,
    verify_group_token,
)
from db.firestore_inmemory import InMemoryFirestoreClient
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository


@pytest.fixture()
def repository(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROUP_AUTH_SIGNING_SECRET", "repository-test-secret")
    repo = MemoryRepository(InMemoryFirestoreClient())
    reset_repository_for_testing(repo)
    AnonymousGroupAuth.reset_for_tests()
    yield repo
    AnonymousGroupAuth.reset_for_tests()
    reset_repository_for_testing(None)


def test_group_rehydrates_after_process_cache_reset(repository: MemoryRepository) -> None:
    created = create_group(
        title="Persistent class",
        skill_ids=["physics-tutor"],
        creator_uid="teacher-1",
        ttl_days=7,
    )

    AnonymousGroupAuth.reset_for_tests()

    restored = get_group(created.group_id)
    assert restored is not None
    assert restored.group_id == created.group_id
    assert restored.creator_uid == "teacher-1"
    assert restored.skill_ids == ("physics-tutor",)


def test_join_group_rehydrates_from_repository_after_restart(repository: MemoryRepository) -> None:
    created = create_group(
        title="Persistent class",
        skill_ids=["physics-tutor"],
        creator_uid="teacher-1",
        ttl_days=7,
    )

    # Simulate a fresh backend process while leaving durable storage intact.
    AnonymousGroupAuth.reset_for_tests()

    joined = join_group(created.group_id, client_ip="192.0.2.10")
    claims = verify_group_token(joined.token)
    assert claims["group_id"] == created.group_id


def test_persisted_revocation_survives_restart(repository: MemoryRepository) -> None:
    created = create_group(
        title="Persistent class",
        skill_ids=["physics-tutor"],
        creator_uid="teacher-1",
        ttl_days=7,
    )
    joined = join_group(created.group_id, client_ip="192.0.2.11")
    delete_group(created.group_id, requesting_uid="teacher-1")

    # Drop all process-local revoked/cache state. The durable row must still
    # prevent the code/token from becoming valid again.
    AnonymousGroupAuth.reset_for_tests()

    assert get_group(created.group_id) is None
    with pytest.raises(GroupRevoked):
        verify_group_token(joined.token)


def test_repository_document_shape_stays_backend_neutral(repository: MemoryRepository) -> None:
    created = create_group(
        title="Portable class",
        skill_ids=["skill-a", "skill-b"],
        creator_uid="teacher-2",
        ttl_days=3,
        max_concurrent_sessions=25,
    )

    stored = repository.get_document("anon_groups", created.group_id)
    assert stored is not None
    assert stored["group_id"] == created.group_id
    assert stored["creator_uid"] == "teacher-2"
    assert stored["skill_ids"] == ["skill-a", "skill-b"]
    assert stored["max_concurrent_sessions"] == 25
    assert "revoked" not in stored
