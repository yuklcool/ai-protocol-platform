"""Regression tests for the production adk.agui.build_agui_adk_agent bridge.

Keep user identity and durable session settings on the same builder used by
chat turns and surface-action runs. The live agent loop is covered by
api_tests/test_stream_skill.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from google.adk.agents import Agent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService


@pytest.fixture
def dummy_agent() -> Agent:
    """An Agent with no tools -- just enough for ADKAgent to accept."""
    return Agent(
        name="unit_test_agent",
        model="gemini-2.5-flash",
        instruction="Unit test agent. Never called.",
        tools=[],
    )


def test_d4_build_agui_adk_agent_threads_user_id_through_to_adk_agent(dummy_agent: Agent) -> None:
    """D4' fix-locking (chat-history-deep-fixes-2): when a caller passes
    ``user_id`` to ``build_agui_adk_agent`` (the production path —
    ``skill_processor.process_skill_request`` now passes ``user.uid``),
    the resulting ADKAgent must resolve that exact value as the user_id
    for every Vertex Agent Engine call. This keeps the
    (app_name, user_id, session_id) triple consistent with the Firestore
    ``chat_sessions/{id}.owner_uid``, so subsequent
    ``GET /api/sessions/{id}/messages`` reads succeed.

    Pre-fix: ``build_agui_adk_agent`` did not accept ``user_id``; calling
    with the kwarg raised TypeError. Post-fix: passes through to ADKAgent.
    """
    from ag_ui.core import RunAgentInput

    from adk.agui import build_agui_adk_agent

    wrapped = build_agui_adk_agent(dummy_agent, user_id="firebase-uid-abc")

    fake_input = RunAgentInput(
        thread_id="thread-xyz",
        run_id="run-1",
        messages=[],
        state={},
        tools=[],
        context=[],
        forwarded_props={},
    )
    resolved = wrapped._get_user_id(fake_input)
    assert resolved == "firebase-uid-abc", (
        f"build_agui_adk_agent must thread user_id through so Vertex creates "
        f"the session under the Firebase auth uid (matching Firestore "
        f"owner_uid). Got {resolved!r} — divergence will reproduce Bugs A'/C."
    )


def test_default_user_id_extractor_diverges_from_firebase_uid(dummy_agent: Agent) -> None:
    """D1' (chat-history-deep-fixes-2 H1): documents the writer-side
    user_id divergence that causes GET /api/sessions/{id}/messages to
    500 with `Session ... does not belong to user`.

    Without an explicit ``user_id`` (the current ``build_agui_adk_agent``
    API), ag_ui_adk's ADKAgent falls back to ``_default_user_extractor``
    which returns ``f"thread_user_{input.thread_id}"`` —
    see ``ag_ui_adk/adk_agent.py:451-454``.

    That value is what ag_ui_adk passes to
    ``VertexAiSessionService.create_session(user_id=...)``. Meanwhile,
    the Firestore index written synchronously by
    ``skills.skill_processor._ensure_session_index`` stores
    ``owner_uid = user.uid`` (Firebase auth uid).

    The two diverge → GET /messages queries Vertex with the Firestore
    owner_uid → Vertex rejects with the documented ValueError → 500.

    Locking the divergence here so the fix (thread user_id through
    build_agui_adk_agent) can be verified end-to-end.
    """
    from ag_ui.core import RunAgentInput

    from adk.agui import build_agui_adk_agent

    wrapped = build_agui_adk_agent(dummy_agent)

    fake_input = RunAgentInput(
        thread_id="thread-abc-123",
        run_id="run-1",
        messages=[],
        state={},
        tools=[],
        context=[],
        forwarded_props={},
    )
    resolved = wrapped._get_user_id(fake_input)
    assert resolved == "thread_user_thread-abc-123", (
        "documents the bug: ag_ui_adk's default extractor uses thread_id, "
        "not the Firebase auth uid; this is what gets stored as the Vertex "
        "session's user_id and is the root cause of the GET /messages 500."
    )


# ---------------------------------------------------------------------------
# Session-durability regression (2026-08-05)
# ---------------------------------------------------------------------------
#
# ag_ui_adk's SessionManager runs a background sweep that DELETES any tracked
# session idle longer than ``session_timeout_seconds``. Both defaults are
# hostile to a persistent chat product — 1200s (20 min) and
# ``delete_session_on_cleanup=True`` — and with Vertex as the store the delete
# is permanent: the session and its events go from Agent Engine, while the
# Firestore ``chat_sessions`` index row (metadata only) survives. Net effect:
# the conversation keeps listing in the left panel and resuming it renders a
# blank chat. Measured on test: 19 of 75 real conversations destroyed.
#
# These tests fail if either knob regresses to its library default.


def test_build_agui_adk_agent_disables_session_cleanup_deletion(dummy_agent: Agent) -> None:
    """Same guarantee on the chat path (``build_agui_adk_agent``), which is the
    builder every real chat turn and surface-action run goes through.

    Reads ``from_app``'s kwargs, not the constructor's: v6.23.0 COMPACTION-WIRE
    switched this builder to ``ADKAgent.from_app(app, ...)`` so the deployment's
    App (and its ``events_compaction_config``) reaches the Runner. The session
    guarantee is unchanged and, if anything, more fragile now — ``from_app``
    re-declares these knobs with ag_ui_adk's hostile defaults, so they must
    still be passed explicitly.

    ``tests/unit/test_compaction_reaches_chat_runner.py`` asserts the same
    guarantee against the REAL ``SessionManager`` rather than a mock; keep both.
    A mock proves we passed the argument, the real manager proves it took
    effect — and the manager is a singleton that silently discards kwargs after
    first init, which a mock can never catch.
    """
    from adk.agui import build_agui_adk_agent

    with patch("adk.agui.ADKAgent") as mock_adk_agent:
        build_agui_adk_agent(
            dummy_agent,
            user_id="uid-1",
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            artifact_service=InMemoryArtifactService(),
        )

        assert mock_adk_agent.call_args is None, (
            "build_agui_adk_agent called ADKAgent(...) directly again — that "
            "leaves _app None and the Runner without an App, which is exactly "
            "the bug that made compaction dead code. Use from_app()."
        )
        kwargs = mock_adk_agent.from_app.call_args.kwargs
        assert kwargs["delete_session_on_cleanup"] is False, (
            "ag_ui_adk would permanently delete idle sessions from Vertex Agent "
            "Engine, destroying the user's conversation history"
        )
        assert kwargs["session_timeout_seconds"] > 1200
        assert kwargs["use_thread_id_as_session_id"] is True, (
            "from_app defaults this to False, which mints a fresh ADK session "
            "per turn and discards conversation memory between turns"
        )
