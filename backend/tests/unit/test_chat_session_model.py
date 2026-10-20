"""Unit tests for ChatSessionIndex model and can_access() integration.

Exhaustive tagged/private/domain/specific truth table lives in
test_access_context.py. Here we verify:
  - ChatSessionIndex validates with all required fields
  - owner_id property satisfies _HasAccess protocol
  - can_access() makes the right decisions for private and tagged sessions
  - list_sessions_for_document post-filtering (mocked Firestore)
"""

from __future__ import annotations

from datetime import UTC, datetime

from auth.access_context import AccessContext, can_access
from db.models.access import AccessControl
from db.models.chat_session import ChatSessionIndex


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _make_session(
    session_id: str = "sess-1",
    owner_uid: str = "user-a",
    ac: AccessControl | None = None,
    document_ids: list[str] | None = None,
) -> ChatSessionIndex:
    return ChatSessionIndex(
        sessionId=session_id,
        tenantId="test-tenant",
        documentIds=document_ids if document_ids is not None else ["doc-1"],
        skillId="skill-1",
        ownerUid=owner_uid,
        accessControl=ac or AccessControl(type="private"),
        firstMessageAt=_utcnow(),
        lastMessageAt=_utcnow(),
    )


# --- Model validation ---


class TestChatSessionIndexModel:
    def test_required_fields(self):
        s = _make_session()
        assert s.session_id == "sess-1"
        assert s.owner_uid == "user-a"
        assert s.skill_id == "skill-1"
        assert s.turn_count == 0
        assert s.archived_at is None
        assert s.title is None

    def test_owner_id_property(self):
        s = _make_session(owner_uid="uid-123")
        assert s.owner_id == "uid-123"

    def test_snake_and_alias_access(self):
        s = _make_session()
        assert s.session_id == "sess-1"  # snake_case access
        dumped = s.model_dump(by_alias=True)
        assert "sessionId" in dumped
        assert "ownerUid" in dumped
        assert dumped["sessionId"] == "sess-1"

    def test_document_ids_default_empty(self):
        s = _make_session(document_ids=[])
        assert s.document_ids == []

    def test_document_ids_multi(self):
        s = _make_session(document_ids=["doc-a", "doc-b"])
        assert s.document_ids == ["doc-a", "doc-b"]

    def test_tagged_access_control(self):
        ac = AccessControl(type="tagged", tags=["finance"])
        s = _make_session(ac=ac)
        assert s.access_control.tags == ["finance"]


# --- can_access() truth table for ChatSessionIndex ---


class TestCanAccessForChatSession:
    def _ctx(self, uid="user-b", tags=()) -> AccessContext:
        return AccessContext(uid=uid, email="b@example.com", domain="example.com", group_tags=frozenset(tags))

    def test_owner_can_access_private(self):
        s = _make_session(owner_uid="owner-x", ac=AccessControl(type="private"))
        ctx = self._ctx(uid="owner-x")
        assert can_access(s.access_control, ctx, s.owner_id) is True

    def test_non_owner_denied_private(self):
        s = _make_session(owner_uid="owner-x", ac=AccessControl(type="private"))
        ctx = self._ctx(uid="other")
        assert can_access(s.access_control, ctx, s.owner_id) is False

    def test_tagged_viewer_with_matching_tag(self):
        s = _make_session(ac=AccessControl(type="tagged", tags=["finance"]))
        ctx = self._ctx(tags=["finance", "legal"])
        assert can_access(s.access_control, ctx, s.owner_id) is True

    def test_tagged_viewer_no_matching_tag(self):
        s = _make_session(ac=AccessControl(type="tagged", tags=["finance"]))
        ctx = self._ctx(tags=["engineering"])
        assert can_access(s.access_control, ctx, s.owner_id) is False

    def test_tagged_viewer_empty_tags_denied(self):
        s = _make_session(ac=AccessControl(type="tagged", tags=["finance"]))
        ctx = self._ctx(tags=[])
        assert can_access(s.access_control, ctx, s.owner_id) is False

    def test_public_session_accessible_to_anyone(self):
        s = _make_session(ac=AccessControl(type="public"))
        ctx = self._ctx(uid="random-user")
        assert can_access(s.access_control, ctx, s.owner_id) is True

    def test_can_access_via_ctx_method(self):
        """AccessContext.can_access() delegates to the global evaluator."""
        s = _make_session(owner_uid="me", ac=AccessControl(type="private"))
        ctx = self._ctx(uid="me")
        assert ctx.can_access(s) is True


# --- list_sessions_for_document post-filter (mocked) ---


class TestListSessionsForDocument:
    def _ctx(self, uid="viewer", tags=()):
        return AccessContext(uid=uid, group_tags=frozenset(tags))

    def _seed(self, *sessions):
        from db.chat_sessions import _to_document
        from db.persistence import get_repository, reset_repository_for_testing
        from db.repositories.memory import MemoryRepository

        reset_repository_for_testing(MemoryRepository())

        for session in sessions:
            get_repository().set_document("chat_sessions", session.session_id, _to_document(session))

    def test_mine_filter_excludes_others(self):
        from db.chat_sessions import list_sessions_for_document

        self._seed(
            _make_session("s1", owner_uid="viewer"),
            _make_session("s2", owner_uid="other", ac=AccessControl(type="tagged", tags=["shared"])),
        )
        rows, _ = list_sessions_for_document("doc-1", self._ctx(tags=["shared"]), filter="mine")
        assert [row.session_id for row in rows] == ["s1"]

    def test_team_filter_excludes_own(self):
        from db.chat_sessions import list_sessions_for_document

        self._seed(
            _make_session("s1", owner_uid="viewer", ac=AccessControl(type="tagged", tags=["shared"])),
            _make_session("s2", owner_uid="alice", ac=AccessControl(type="tagged", tags=["shared"])),
        )
        rows, _ = list_sessions_for_document("doc-1", self._ctx(tags=["shared"]), filter="team")
        assert [row.session_id for row in rows] == ["s2"]

    def test_inaccessible_sessions_excluded(self):
        from db.chat_sessions import list_sessions_for_document

        private = _make_session("private", owner_uid="bob")
        self._seed(private)
        assert list_sessions_for_document("doc-1", self._ctx()) == ([], None)
