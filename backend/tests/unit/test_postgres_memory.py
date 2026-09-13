from __future__ import annotations

import pytest
from google.adk.events import Event
from google.adk.sessions import Session
from google.genai import types

from adk.postgres_memory import PostgresMemoryService
from db.firestore_inmemory import InMemoryFirestoreClient
from db.repositories.memory import MemoryRepository


def _repository() -> MemoryRepository:
    # backend/tests/conftest.py intentionally replaces db.firestore._client
    # with a MagicMock to prevent accidental GCP calls. These tests need a real
    # repository because they exercise persistence semantics, so inject the
    # isolated in-memory Firestore implementation explicitly.
    return MemoryRepository(client=InMemoryFirestoreClient())


def _event(text: str, *, author: str = "user") -> Event:
    return Event(
        invocation_id="inv-1",
        author=author,
        content=types.Content(role=author, parts=[types.Part(text=text)]),
    )


@pytest.mark.asyncio
async def test_memory_survives_service_reconstruction_with_same_repository():
    repository = _repository()
    first = PostgresMemoryService(repository=repository)
    session = Session(
        id="session-1",
        app_name="aitana_platform",
        user_id="user-a",
        events=[_event("The lighting controller uses DALI-2."), _event("Unrelated note")],
    )

    await first.add_session_to_memory(session)

    # Reconstruct the service to model a backend process restart. The durable
    # repository remains; the service's in-process state does not.
    second = PostgresMemoryService(repository=repository)
    result = await second.search_memory(
        app_name="aitana_platform",
        user_id="user-a",
        query="DALI-2",
    )

    assert len(result.memories) == 1
    assert result.memories[0].content.parts[0].text == "The lighting controller uses DALI-2."


@pytest.mark.asyncio
async def test_memory_is_user_scoped():
    repository = _repository()
    service = PostgresMemoryService(repository=repository)

    await service.add_session_to_memory(
        Session(
            id="session-a",
            app_name="aitana_platform",
            user_id="user-a",
            events=[_event("tenant A secret phrase")],
        )
    )
    await service.add_session_to_memory(
        Session(
            id="session-b",
            app_name="aitana_platform",
            user_id="user-b",
            events=[_event("tenant B secret phrase")],
        )
    )

    result = await service.search_memory(
        app_name="aitana_platform",
        user_id="user-a",
        query="tenant",
    )

    texts = [memory.content.parts[0].text for memory in result.memories]
    assert texts == ["tenant A secret phrase"]


@pytest.mark.asyncio
async def test_add_events_is_idempotent_by_event_id():
    repository = _repository()
    service = PostgresMemoryService(repository=repository)
    event = _event("remember this controller id")

    await service.add_events_to_memory(
        app_name="aitana_platform",
        user_id="user-a",
        session_id="session-1",
        events=[event],
    )
    await service.add_events_to_memory(
        app_name="aitana_platform",
        user_id="user-a",
        session_id="session-1",
        events=[event],
    )

    result = await service.search_memory(
        app_name="aitana_platform",
        user_id="user-a",
        query="controller",
    )
    assert len(result.memories) == 1


@pytest.mark.asyncio
async def test_unicode_substring_recall_supports_chinese_text():
    repository = _repository()
    service = PostgresMemoryService(repository=repository)
    await service.add_session_to_memory(
        Session(
            id="session-cn",
            app_name="aitana_platform",
            user_id="user-cn",
            events=[_event("这个项目使用智慧照明控制系统")],
        )
    )

    result = await service.search_memory(
        app_name="aitana_platform",
        user_id="user-cn",
        query="智慧照明",
    )
    assert len(result.memories) == 1
