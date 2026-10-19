"""Unit tests for CHAT-HISTORY M2 session callbacks.

Covers:
- make_session_tracker: creates index on first turn, skips on subsequent turns
- make_after_agent_response: bumps counter, flushes every 5 turns, generates
  title after turn 2 (not turn 1, not turn 3), never crashes on errors
- _derive_access_control: falls back to private when document unavailable
- _try_generate_title: returns None on any exception
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from adk.callbacks import (
    _STATE_INITIALIZED,
    _STATE_TURN_COUNT,
    _TURN_FLUSH_INTERVAL,
    _derive_access_control,
    _try_generate_title,
    make_after_agent_response,
    make_session_tracker,
)
from db.models.access import AccessControl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    session_id="sess-1",
    initialized=False,
    turn_count=0,
    skill_id="skill-x",
    document_ids: list[str] | None = None,
):
    state = {
        "skill_id": skill_id,
        "document_ids": document_ids or [],
    }
    if initialized:
        state[_STATE_INITIALIZED] = True
        state[_STATE_TURN_COUNT] = turn_count

    session = MagicMock()
    session.id = session_id
    session.events = []

    ctx = MagicMock()
    ctx.state = state
    ctx.session = session
    return ctx


# ---------------------------------------------------------------------------
# make_session_tracker
# ---------------------------------------------------------------------------


class TestMakeSessionTracker:
    @patch("adk.callbacks.create_session_index", create=True)
    @patch("db.chat_sessions.create_session_index")
    def test_creates_index_on_first_turn(self, mock_create, _mock2):
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=False)

        with patch("adk.callbacks._derive_access_control", return_value=AccessControl(type="private")):
            tracker(ctx)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["owner_uid"] == "uid-owner"
        assert call_kwargs["document_ids"] == []
        assert ctx.state[_STATE_INITIALIZED] is True
        assert ctx.state[_STATE_TURN_COUNT] == 0

    @patch("adk.callbacks.create_session_index", create=True)
    @patch("db.chat_sessions.create_session_index")
    def test_passes_full_document_ids_list(self, mock_create, _mock2):
        """First-turn index creation must include every doc the user attached
        so list_sessions_for_document(array_contains) finds the session under
        each of its docs' history panels."""
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=False, document_ids=["docA", "docB", "docC"])

        with patch("adk.callbacks._derive_access_control", return_value=AccessControl(type="private")):
            tracker(ctx)

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["document_ids"] == ["docA", "docB", "docC"]

    @patch("db.chat_sessions.create_session_index")
    def test_skips_on_subsequent_turns(self, mock_create):
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=True, turn_count=3)

        tracker(ctx)

        mock_create.assert_not_called()

    @patch("adk.callbacks.get_session_index", create=True)
    @patch("db.chat_sessions.create_session_index")
    def test_create_session_index_is_idempotent(self, mock_create, mock_get):
        """B1 idempotency (chat-history-fixes): when ``process_skill_request``
        has already written the index synchronously, the before_agent_callback
        must skip its own write — otherwise it clobbers any title / turnCount /
        documentIds updates that landed between the synchronous write and the
        callback firing.

        The callback should observe the existing row (via ``get_session_index``)
        and short-circuit, marking state as initialised so subsequent turns
        also skip. Pre-fix the callback only checked the in-memory state flag,
        so it always re-wrote on turn 1.
        """
        from datetime import UTC, datetime

        from db.models.chat_session import ChatSessionIndex

        existing = ChatSessionIndex(
            sessionId="sess-1",
            skillId="skill-x",
            ownerUid="uid-owner",
            accessControl=AccessControl(type="private"),
            firstMessageAt=datetime.now(UTC),
            lastMessageAt=datetime.now(UTC),
        )
        mock_get.return_value = existing
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=False)

        tracker(ctx)

        mock_create.assert_not_called()
        assert ctx.state[_STATE_INITIALIZED] is True, (
            "B1 idempotency: callback must mark state initialised when row already "
            "exists, so future turns short-circuit on the in-memory flag."
        )

    @patch("db.chat_sessions.create_session_index", side_effect=Exception("Firestore down"))
    def test_does_not_crash_on_firestore_error(self, _mock):
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=False)

        with patch("adk.callbacks._derive_access_control", return_value=AccessControl(type="private")):
            tracker(ctx)  # must not raise

        assert _STATE_INITIALIZED not in ctx.state  # flag not set on failure

    def test_no_op_when_state_is_none(self):
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = MagicMock()
        ctx.state = None
        tracker(ctx)  # must not raise

    def test_no_op_when_session_id_missing(self):
        tracker = make_session_tracker("uid-owner", "skill-x")
        ctx = _make_ctx(initialized=False)
        ctx.session.id = None
        tracker(ctx)  # must not raise


# ---------------------------------------------------------------------------
# make_after_agent_response
# ---------------------------------------------------------------------------


class TestMakeAfterAgentResponse:
    @patch("db.chat_sessions.update_session_fields")
    def test_increments_turn_count(self, mock_update):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=5)

        cb(ctx)

        assert ctx.state[_STATE_TURN_COUNT] == 6

    @patch("db.chat_sessions.update_session_fields")
    def test_no_flush_on_turn_3(self, mock_update):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=2)  # will become 3

        cb(ctx)

        mock_update.assert_not_called()

    @patch("db.chat_sessions.update_session_fields")
    def test_flushes_on_turn_5(self, mock_update):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=_TURN_FLUSH_INTERVAL - 1)  # will become 5

        cb(ctx)

        mock_update.assert_called_once()

    @patch("adk.callbacks._try_generate_title", return_value="Revenue drivers Q1")
    @patch("db.chat_sessions.update_session_fields")
    def test_generates_title_after_turn_2(self, mock_update, mock_title):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=1)  # will become 2

        cb(ctx)

        mock_title.assert_called_once()
        update_kwargs = mock_update.call_args[0][1]
        assert update_kwargs["title"] == "Revenue drivers Q1"

    @patch("adk.callbacks._try_generate_title", return_value="some title")
    @patch("db.chat_sessions.update_session_fields")
    def test_no_title_on_turn_1(self, mock_update, mock_title):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=0)  # will become 1

        cb(ctx)

        mock_title.assert_not_called()

    @patch("adk.callbacks._try_generate_title", return_value="some title")
    @patch("db.chat_sessions.update_session_fields")
    def test_no_title_on_turn_3(self, mock_update, mock_title):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=2)  # will become 3

        cb(ctx)

        mock_title.assert_not_called()

    @patch("db.chat_sessions.update_session_fields", side_effect=Exception("Firestore error"))
    def test_does_not_crash_on_update_error(self, _mock):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=_TURN_FLUSH_INTERVAL - 1)

        cb(ctx)  # must not raise

    def test_no_op_when_not_initialized(self):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=False)

        with patch("db.chat_sessions.update_session_fields") as mock_update:
            cb(ctx)
            mock_update.assert_not_called()

    @patch("adk.callbacks.add_session_documents", create=True)
    @patch("db.chat_sessions.update_session_fields")
    def test_after_agent_callback_does_not_restore_old_attachment_selection(self, _mock_update, mock_add):
        """轮次计数刷新不能把旧轮次附件重新写回当前选择。"""
        cb = make_after_agent_response()
        ctx = _make_ctx(
            initialized=True,
            turn_count=_TURN_FLUSH_INTERVAL - 1,  # will become 5 → flush
            document_ids=["docA", "docB", "docC"],
        )

        cb(ctx)

        mock_add.assert_not_called()

    @patch("adk.callbacks._try_generate_title")
    @patch("db.chat_sessions.update_session_fields")
    def test_title_regenerates_when_turn_two_returns_empty(self, mock_update, mock_title):
        """B3 (chat-history-fixes): if turn-2 title generation returns ``None``
        (thin context — e.g. a one-word user message), the callback must retry
        on a later flush turn. Pre-fix, ``needs_title_gen = turn_count == 2``
        only — so a None at turn 2 meant the session never got a title.

        Post-fix: condition becomes ``turn_count == 2 or (turn_count >= 4 and
        not state.get("titleSet"))``. Successful generation sets
        ``state["titleSet"] = True`` so we retry only when needed.
        """
        cb = make_after_agent_response()

        # --- Turn 2: generation returns None (thin context) ---
        mock_title.return_value = None
        ctx = _make_ctx(initialized=True, turn_count=1)  # → 2
        cb(ctx)
        assert mock_title.call_count == 1, "first attempt fires on turn 2"
        assert not ctx.state.get("titleSet"), "B3: titleSet must remain False when generation returned None"

        # --- Turn 5 (next flush boundary): retry, this time succeeds ---
        mock_title.return_value = "Generated title"
        ctx.state[_STATE_TURN_COUNT] = 4  # → 5, multiple of _TURN_FLUSH_INTERVAL
        cb(ctx)

        assert mock_title.call_count == 2, (
            "B3: title generation must be retried at turn 5 because "
            "state['titleSet'] was never set on turn 2 (generation returned None)."
        )
        # Find the call that wrote the new title
        title_writes = [c.args[1] for c in mock_update.call_args_list if c.args[1].get("title") == "Generated title"]
        assert title_writes, (
            "B3: turn-5 retry must include title='Generated title' in the "
            f"Firestore update payload. Got: {[c.args[1] for c in mock_update.call_args_list]}"
        )
        assert ctx.state.get("titleSet") is True, (
            "B3: successful generation must set state['titleSet']=True so further turns short-circuit the retry path."
        )


# ---------------------------------------------------------------------------
# _derive_access_control
# ---------------------------------------------------------------------------


class TestDeriveAccessControl:
    def test_no_document_id_returns_private(self):
        ac = _derive_access_control(None)
        assert ac.type == "private"

    @patch("db.persistence.get_document", return_value={"accessControl": {"type": "tagged", "tags": ["finance"]}})
    def test_inherits_document_access_control(self, _mock):
        ac = _derive_access_control("doc-abc")
        assert ac.type == "tagged"
        assert ac.tags == ["finance"]

    @patch("db.persistence.get_document", return_value=None)
    def test_falls_back_to_private_when_doc_missing(self, _mock):
        ac = _derive_access_control("doc-missing")
        assert ac.type == "private"

    @patch("db.persistence.get_document", side_effect=Exception("network error"))
    def test_falls_back_to_private_on_error(self, _mock):
        ac = _derive_access_control("doc-xyz")
        assert ac.type == "private"


# ---------------------------------------------------------------------------
# _try_generate_title
# ---------------------------------------------------------------------------


class TestTryGenerateTitle:
    def test_returns_none_on_exception(self):
        session = MagicMock()
        session.events = []

        with patch("db.title_generator.generate_title_fast", side_effect=Exception("model error")):
            result = _try_generate_title(session)

        assert result is None

    def test_returns_none_when_events_empty(self):
        session = MagicMock()
        session.events = []

        with patch("db.title_generator.generate_title_fast", return_value=None):
            result = _try_generate_title(session)

        assert result is None


# ---------------------------------------------------------------------------
# RAG document loader / injector (RAG_DOCUMENTS_ENABLED=true path)
# ---------------------------------------------------------------------------


class TestFirstTurnFlush:
    """Regression (2026-08-05): "I just sent this and it says 52m ago".

    ``lastMessageAt`` drives both the label and the sort order of the history
    sidebar. With the flush debounced to every 5 turns, the first write landed on
    turn 2 (via title generation), so after a single message the row still
    carried the stamp written when the row was CREATED — page-mount time for a
    bootstrap-created row. Observed live on test: a session posted to at 12:12
    rendered "52m ago" because its stamp was the 11:20 mount.
    """

    @patch("db.chat_sessions.update_session_fields")
    def test_turn_1_flushes_last_message_at(self, mock_update):
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=0)  # will become 1

        cb(ctx)

        mock_update.assert_called_once()
        fields = mock_update.call_args[0][1]
        assert fields["turnCount"] == 1
        assert "lastMessageAt" in fields, (
            "without this the sidebar shows the row's creation time, not the message the user just sent"
        )

    @patch("db.chat_sessions.update_session_fields")
    def test_turn_3_still_debounced(self, mock_update):
        """The debounce itself is intact — only turn 1 was carved out."""
        cb = make_after_agent_response()
        ctx = _make_ctx(initialized=True, turn_count=2)  # will become 3

        cb(ctx)

        mock_update.assert_not_called()
