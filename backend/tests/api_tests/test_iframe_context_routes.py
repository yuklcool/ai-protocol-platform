"""MCP App 写入只服从当前 Root 策略和会话、租户边界。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from auth.access_context import build_access_context
from db.models.chat_session import ChatSessionIndex
from db.models.root_agent import RootAgentConfig
from protocols import iframe_context_routes as routes

BODY = {"serverId": "map", "toolName": "show-map", "structuredContent": {"label": "道路照明"}}
PATH = "/api/sessions/session-a/iframe-context"


@pytest.fixture
def setup(monkeypatch):
    user = User(uid="viewer")
    from db.persistence import get_repository, reset_repository_for_testing
    from db.repositories.memory import MemoryRepository

    reset_repository_for_testing(MemoryRepository())
    repo = get_repository()
    ids = ["map-server", "map", "private", "global"]
    for ref in ids:
        repo.set_document("mcp_servers", ref, {"enabled": True, "url": "https://mcp.example.test/mcp"})
    app = FastAPI()
    app.include_router(routes.router)

    async def identity(request: Request):
        request.state.access = build_access_context(user)
        from observability.user_context import set_user_context

        set_user_context(user)
        return user

    app.dependency_overrides[get_current_user] = identity
    now = datetime.now(UTC)
    index = ChatSessionIndex(
        sessionId="session-a",
        skillId="root-agent",
        tenantId="tenant-a",
        ownerUid="viewer",
        accessControl={"type": "private"},
        documentIds=[],
        firstMessageAt=now,
        lastMessageAt=now,
    )
    root = RootAgentConfig(mcpServers=["map"], interaction={"allowSurfaceContextWrites": True})
    server = {"enabled": True}
    service = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace()), append_event=AsyncMock())
    monkeypatch.setattr("protocols._a2ui_surface_shared.get_platform_config", lambda: SimpleNamespace(agent=root))
    monkeypatch.setattr(routes, "get_session_index", lambda *_: index)
    monkeypatch.setattr(routes, "get_document", lambda *_: server)
    monkeypatch.setattr(routes, "get_session_service", lambda: service)
    return TestClient(app), root, index, server, service


def test_authorized_context_uses_namespaced_state(setup):
    client, _, _, _, service = setup
    assert client.post(PATH, json=BODY).status_code == 204
    event = service.append_event.call_args.args[1]
    written = event.actions.state_delta["mcp_app_context.map.show-map"]
    assert written["structuredContent"] == BODY["structuredContent"]
    assert written["_pushedAt"] > 0


@pytest.mark.parametrize("change", ["unbind", "interaction", "disabled", "foreign", "shared"])
def test_revocation_and_isolation_take_effect_on_next_write(setup, change):
    client, root, index, server, service = setup
    assert client.post(PATH, json=BODY).status_code == 204
    if change == "unbind":
        root.mcp_servers.clear()
    elif change == "interaction":
        root.interaction.allow_surface_context_writes = False
    elif change == "disabled":
        server["enabled"] = False
    elif change == "foreign":
        server["scope"] = "unavailable"
    else:
        index.owner_uid = "other"
        index.access_control.type = "public"
    assert client.post(PATH, json=BODY).status_code == 403
    assert service.append_event.call_count == 1


def test_old_session_cannot_restore_old_skill_binding(setup, monkeypatch):
    client, root, index, _, service = setup
    index.skill_id = "old-skill"
    root.mcp_servers.clear()
    monkeypatch.setattr("skills.skill_config.get_skill", lambda *_: pytest.fail("must not read Skill binding"))
    assert client.post(PATH, json=BODY).status_code == 403
    service.append_event.assert_not_called()


def test_missing_session_and_missing_backend(setup, monkeypatch):
    client, _, _, _, service = setup
    service.get_session.return_value = None
    assert client.post(PATH, json=BODY).status_code == 404
    monkeypatch.setattr(routes, "get_session_index", lambda *_: None)
    assert client.post(PATH, json=BODY).status_code == 404
    service.append_event.assert_not_called()


def test_size_schema_and_empty_payload(setup):
    client, _, _, _, service = setup
    assert client.post(PATH, json={**BODY, "structuredContent": {"text": "大" * 4096}}).status_code == 413
    assert client.post(PATH, json={**BODY, "structuredContent": "not an object"}).status_code == 422
    assert client.post(PATH, json={**BODY, "structuredContent": None}).status_code == 204
    service.append_event.assert_not_called()
