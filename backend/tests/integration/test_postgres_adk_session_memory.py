from __future__ import annotations

import os
import uuid

import pytest
from google.adk.events import Event
from google.genai import types

from adk import session as session_mod


pytestmark = pytest.mark.asyncio


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration test")
    return value


async def test_adk_session_and_memory_survive_service_reconstruction(monkeypatch):
    database_url = _database_url()
    suffix = uuid.uuid4().hex[:12]
    app_name = f"ci-session-{suffix}"
    user_id = f"user-{suffix}"
    session_id = f"session-{suffix}"
    remembered_phrase = f"controller-{suffix} uses DALI-2"

    monkeypatch.setenv("SESSION_BACKEND", "postgres")
    monkeypatch.setenv("MEMORY_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", database_url)

    session_mod._reset_session_service_for_tests()
    session_mod._reset_memory_service_for_tests()

    first_session_service = session_mod.get_session_service()
    created = await first_session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    event = Event(
        invocation_id=f"inv-{suffix}",
        author="user",
        content=types.Content(
            role="user",
            parts=[types.Part(text=remembered_phrase)],
        ),
    )
    await first_session_service.append_event(created, event)

    # Rebuild the ADK DatabaseSessionService. This is the important restart
    # boundary: no Python object from the first service may be required.
    session_mod._reset_session_service_for_tests()
    second_session_service = session_mod.get_session_service()
    restored = await second_session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    assert restored is not None
    assert restored.id == session_id
    assert any(
        part.text == remembered_phrase
        for restored_event in restored.events
        if restored_event.content
        for part in restored_event.content.parts or []
        if part.text
    )

    first_memory_service = session_mod.get_memory_service()
    await first_memory_service.add_session_to_memory(restored)

    # Rebuild our MemoryService too. The recall must come from PostgreSQL, not
    # from an in-process list/cache held by the first instance.
    session_mod._reset_memory_service_for_tests()
    second_memory_service = session_mod.get_memory_service()
    recalled = await second_memory_service.search_memory(
        app_name=app_name,
        user_id=user_id,
        query=f"controller-{suffix}",
    )

    assert any(
        remembered_phrase in (part.text or "")
        for memory in recalled.memories
        for part in memory.content.parts or []
    )

    # Keep the shared CI PostgreSQL clean. Memory rows live in a randomized
    # per-user collection and the whole CI database is ephemeral; the ADK
    # session can be removed through the public service contract.
    await second_session_service.delete_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
