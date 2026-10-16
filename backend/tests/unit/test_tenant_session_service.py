from unittest.mock import patch

import pytest
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService

from adk.tenant_session_service import TenantScopedSessionService


@pytest.mark.asyncio
async def test_app_user_state_and_events_do_not_cross_same_uid_tenants():
    delegate = InMemorySessionService()
    service = TenantScopedSessionService(delegate)
    with patch("adk.tenant_session_service.get_current_tenant_id", return_value="tenant-a"):
        a = await service.create_session(app_name="root-agent", user_id="same", session_id="session")
        await service.append_event(
            a, Event(author="user", actions=EventActions(state_delta={"user:secret": "a", "app:secret": "a"}))
        )
        assert a.app_name == "root-agent"
        assert a.state["user:secret"] == "a"
    with patch("adk.tenant_session_service.get_current_tenant_id", return_value="tenant-b"):
        assert await service.get_session(app_name="root-agent", user_id="same", session_id="session") is None
        b = await service.create_session(app_name="root-agent", user_id="same", session_id="session")
        assert "user:secret" not in b.state and "app:secret" not in b.state
        assert len((await service.list_sessions(app_name="root-agent", user_id="same")).sessions) == 1
        await service.delete_session(app_name="root-agent", user_id="same", session_id="session")
    reconstructed = TenantScopedSessionService(delegate)
    with patch("adk.tenant_session_service.get_current_tenant_id", return_value="tenant-a"):
        a = await reconstructed.get_session(app_name="root-agent", user_id="same", session_id="session")
        assert a.state["app:secret"] == "a"
    with patch("adk.tenant_session_service.get_current_tenant_id", return_value=""):
        with pytest.raises(PermissionError):
            await service.list_sessions(app_name="root-agent", user_id="same")
