from __future__ import annotations

from unittest.mock import patch

from adk import session as session_mod


def setup_function():
    session_mod._reset_session_service_for_tests()
    session_mod._reset_memory_service_for_tests()


def teardown_function():
    session_mod._reset_session_service_for_tests()
    session_mod._reset_memory_service_for_tests()


def test_postgres_session_backend_normalizes_asyncpg_url_and_overrides_legacy_memory_flag():
    env = {
        "SESSION_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:pass@postgres:5432/aip",
        "AITANA_LOCAL_SESSION": "memory",
    }
    sentinel = object()
    with patch.dict("os.environ", env, clear=True), patch(
        "google.adk.sessions.DatabaseSessionService", return_value=sentinel
    ) as factory:
        service = session_mod.get_session_service()

    assert service is sentinel
    factory.assert_called_once_with(db_url="postgresql+asyncpg://user:pass@postgres:5432/aip")


def test_postgres_session_uri_uses_async_driver():
    env = {
        "SESSION_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:pass@postgres:5432/aip",
    }
    with patch.dict("os.environ", env, clear=True):
        assert session_mod.get_session_service_uri() == "postgresql+asyncpg://user:pass@postgres:5432/aip"


def test_postgres_memory_backend_uses_same_database_and_is_singleton():
    env = {
        "MEMORY_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:pass@postgres:5432/aip",
        "AITANA_LOCAL_SESSION": "memory",
    }
    sentinel = object()
    with patch.dict("os.environ", env, clear=True), patch(
        "adk.postgres_memory.PostgresMemoryService", return_value=sentinel
    ) as factory:
        first = session_mod.get_memory_service()
        second = session_mod.get_memory_service()

    assert first is sentinel
    assert second is sentinel
    factory.assert_called_once_with("postgresql://user:pass@postgres:5432/aip")


def test_postgres_memory_uri_does_not_expose_database_credentials():
    env = {
        "MEMORY_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:super-secret@postgres:5432/aip",
    }
    with patch.dict("os.environ", env, clear=True):
        uri = session_mod.get_memory_service_uri()

    assert uri == "aip-postgres-memory://default"
    assert "super-secret" not in uri


def test_legacy_defaults_are_unchanged_without_new_backend_envs():
    with patch.dict("os.environ", {}, clear=True):
        assert session_mod.session_backend_name() == "memory"
        assert session_mod.memory_backend_name() == "memory"

    with patch.dict(
        "os.environ",
        {"AGENT_ENGINE_ID": "projects/p/locations/l/reasoningEngines/123"},
        clear=True,
    ):
        assert session_mod.session_backend_name() == "vertex"
        assert session_mod.memory_backend_name() == "vertex"
