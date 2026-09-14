from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from google.adk.events import Event, EventActions

from adk import session as session_mod
from adk.callbacks import A2UI_SURFACE_STATE_PREFIX
from protocols.sessions_route import _state_to_a2ui_surfaces


pytestmark = pytest.mark.asyncio


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration test")
    return value


async def _append_state_delta(service, session, *, invocation_id: str, delta: dict[str, str]) -> None:
    await service.append_event(
        session,
        Event(
            invocation_id=invocation_id,
            author="user",
            actions=EventActions(state_delta=delta),
            timestamp=time.time(),
        ),
    )


async def test_a2ui_surface_and_client_edits_survive_postgres_reconstruction(monkeypatch):
    """The workbench must rehydrate from durable ADK session state.

    This exercises the exact persistence contract used in production:

    * the result->A2UI emitter stores ``a2ui_surface:{surfaceId}`` in session
      state;
    * ``DatabaseSessionService`` persists that state in PostgreSQL;
    * the history endpoint converts it back to the live ``A2UI_SURFACE`` replay
      payload through ``_state_to_a2ui_surfaces``;
    * client-side data-model edits are stored in the same stash and materialise
      as a final ``updateDataModel`` message on resume.

    The service is reconstructed twice so no in-process Session object can make
    this test pass accidentally.
    """
    database_url = _database_url()
    suffix = uuid.uuid4().hex[:12]
    app_name = f"ci-a2ui-{suffix}"
    user_id = f"user-{suffix}"
    session_id = f"session-{suffix}"
    surface_id = f"obligation-analysis:{suffix}"
    state_key = f"{A2UI_SURFACE_STATE_PREFIX}{surface_id}"

    monkeypatch.setenv("SESSION_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", database_url)
    session_mod._reset_session_service_for_tests()

    first = session_mod.get_session_service()
    session = await first.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    canonical_messages = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": [{"id": "root", "component": {"Text": {"text": "Persistent UI"}}}],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": surface_id,
                "value": {"payload": {"status": "canonical"}},
            },
        },
    ]
    stash = {
        "surfaceId": surface_id,
        "messages": canonical_messages,
        "artifact": {"kind": "obligation-analysis", "title": "Persistent result"},
        "sourceId": f"inv-{suffix}:map_obligations:1",
        "toolName": "map_obligations",
        "createdAt": time.time() * 1000,
    }
    await _append_state_delta(
        first,
        session,
        invocation_id=f"surface-{suffix}",
        delta={state_key: json.dumps(stash)},
    )

    # Backend restart boundary #1: the replay must come from PostgreSQL.
    session_mod._reset_session_service_for_tests()
    second = session_mod.get_session_service()
    restored = await second.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    assert restored is not None

    replay = _state_to_a2ui_surfaces(restored.state)
    assert len(replay) == 1
    assert replay[0]["surfaceId"] == surface_id
    assert replay[0]["sourceId"] == stash["sourceId"]
    assert replay[0]["artifact"] == stash["artifact"]
    assert replay[0]["messages"] == canonical_messages

    # Mirror POST /surface-data: preserve canonical messages and layer the
    # client's latest root data model on top of the replay.
    edited_model = {
        "payload": {"status": "canonical"},
        "scenario": {"deadlineDelta": {"COD": 21}, "waive": {"payment": True}},
    }
    edited_stash = {
        **stash,
        "clientDataModel": {"value": edited_model, "updatedAt": time.time() * 1000},
    }
    await _append_state_delta(
        second,
        restored,
        invocation_id=f"surface-edit-{suffix}",
        delta={state_key: json.dumps(edited_stash)},
    )

    # Backend restart boundary #2: edited workbench state must also survive.
    session_mod._reset_session_service_for_tests()
    third = session_mod.get_session_service()
    restored_after_edit = await third.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    assert restored_after_edit is not None

    replay_after_edit = _state_to_a2ui_surfaces(restored_after_edit.state)
    assert len(replay_after_edit) == 1
    messages = replay_after_edit[0]["messages"]
    assert messages[:-1] == canonical_messages
    assert messages[-1] == {
        "version": "v0.9",
        "updateDataModel": {"surfaceId": surface_id, "value": edited_model},
    }

    await third.delete_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
