"""Phase 3 regression tests for chat-session tenant isolation.

Sharing ACLs are intentionally exercised with permissive values in several
cases: the stable tenant boundary must win even when a session is public or the
same uid exists in two tenants.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auth.access_context import AccessContext
from auth.models import User
from db.chat_sessions import (
    create_session_index,
    get_session_index,
    list_sessions_for_document,
    list_sessions_for_skill,
    most_recent_session_for_user,
    session_in_tenant,
    update_session_fields,
)
from db.models.access import AccessControl
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory
from observability.tenant_context import set_tenant_context


@pytest.fixture()
def repo():
    repository = MemoryRepository()
    reset_repository_for_testing(repository)
    yield repository
    reset_repository_for_testing(None)


def _tenant(repository: MemoryRepository, tenant_id: str, *domains: str) -> None:
    TenantDirectory(repository).put(TenantConfig(tenantId=tenant_id, domains=list(domains)))


def _create(
    *,
    session_id: str,
    tenant_id: str,
    owner_uid: str = "shared-uid",
    owner_domain: str = "",
    access_type: str = "public",
    document_ids: list[str] | None = None,
):
    return create_session_index(
        session_id=session_id,
        skill_id="skill-1",
        owner_uid=owner_uid,
        tenant_id=tenant_id,
        owner_domain=owner_domain,
        access_control=AccessControl(type=access_type),
        document_ids=document_ids,
        first_message_at=datetime.now(UTC),
    )


def test_public_acl_cannot_cross_tenant(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a")
    _tenant(repo, "tenant-b")
    session = _create(session_id="a-session", tenant_id="tenant-a", access_type="public")

    ctx_a = AccessContext(uid="viewer", tenant_id="tenant-a")
    ctx_b = AccessContext(uid="viewer", tenant_id="tenant-b")

    assert ctx_a.can_access(session) is True
    assert ctx_b.can_access(session) is False


def test_same_uid_history_is_partitioned_by_tenant(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a")
    _tenant(repo, "tenant-b")
    _create(session_id="a1", tenant_id="tenant-a", owner_uid="same-uid")
    _create(session_id="b1", tenant_id="tenant-b", owner_uid="same-uid")

    a_rows, _ = list_sessions_for_skill(None, "same-uid", tenant_id="tenant-a")
    b_rows, _ = list_sessions_for_skill(None, "same-uid", tenant_id="tenant-b")

    assert [row.session_id for row in a_rows] == ["a1"]
    assert [row.session_id for row in b_rows] == ["b1"]


def test_recent_session_is_partitioned_by_tenant(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a")
    _tenant(repo, "tenant-b")
    _create(session_id="a-recent", tenant_id="tenant-a", owner_uid="same-uid")
    _create(session_id="b-recent", tenant_id="tenant-b", owner_uid="same-uid")

    assert [row.session_id for row in most_recent_session_for_user("same-uid", tenant_id="tenant-a")] == [
        "a-recent"
    ]
    assert [row.session_id for row in most_recent_session_for_user("same-uid", tenant_id="tenant-b")] == [
        "b-recent"
    ]


def test_document_session_list_filters_tenant_before_acl(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a")
    _tenant(repo, "tenant-b")
    _create(session_id="a-doc", tenant_id="tenant-a", document_ids=["doc-1"], access_type="public")
    _create(session_id="b-doc", tenant_id="tenant-b", document_ids=["doc-1"], access_type="public")

    rows, _ = list_sessions_for_document(
        "doc-1",
        AccessContext(uid="viewer", tenant_id="tenant-a"),
    )
    assert [row.session_id for row in rows] == ["a-doc"]


def test_legacy_session_hydrates_only_through_registered_domain_mapping(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a", "legacy.example")
    now = datetime.now(UTC).isoformat()
    repo.set_document(
        "chat_sessions",
        "legacy-session",
        {
            "sessionId": "legacy-session",
            "skillId": "skill-1",
            "ownerUid": "legacy-user",
            "ownerDomain": "legacy.example",
            "accessControl": {"type": "public"},
            "firstMessageAt": now,
            "lastMessageAt": now,
            "archivedAt": None,
        },
    )

    session = get_session_index("legacy-session")
    assert session is not None
    assert session.tenant_id == "tenant-a"
    assert session_in_tenant(session, "tenant-a") is True
    assert AccessContext(uid="viewer", tenant_id="tenant-a").can_access(session) is True
    assert AccessContext(uid="viewer", tenant_id="tenant-b").can_access(session) is False


def test_unmapped_legacy_session_fails_closed(repo: MemoryRepository) -> None:
    now = datetime.now(UTC).isoformat()
    repo.set_document(
        "chat_sessions",
        "orphan-session",
        {
            "sessionId": "orphan-session",
            "skillId": "skill-1",
            "ownerUid": "same-uid",
            "ownerDomain": "unknown.example",
            "accessControl": {"type": "public"},
            "firstMessageAt": now,
            "lastMessageAt": now,
            "archivedAt": None,
        },
    )

    session = get_session_index("orphan-session")
    assert session is not None
    assert session.tenant_id == ""
    assert AccessContext(uid="same-uid", tenant_id="tenant-a").is_owner(session) is False
    assert AccessContext(uid="same-uid", tenant_id="tenant-a").can_access(session) is False


def test_cross_tenant_mutation_is_rejected_even_for_same_uid(repo: MemoryRepository) -> None:
    _tenant(repo, "tenant-a")
    _tenant(repo, "tenant-b")
    _create(session_id="protected", tenant_id="tenant-a", owner_uid="same-uid")

    set_tenant_context(User(uid="same-uid", tenant_id="tenant-b"))
    with pytest.raises(PermissionError, match="another tenant"):
        update_session_fields("protected", {"title": "must not write"})

    stored = repo.get_document("chat_sessions", "protected")
    assert stored is not None
    assert stored.get("title") is None
