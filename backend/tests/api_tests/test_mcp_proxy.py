"""Root MCP 授权及代理传输边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from auth.access_context import build_access_context
from db.models.root_agent import RootAgentConfig
from protocols import mcp_proxy


@pytest.fixture
def setup(monkeypatch):
    user = User(
        uid="viewer", email="viewer@example.com", tenant_id="tenant-a", permission_group_ids=frozenset({"maps"})
    )
    from auth.capability_access import GROUP_COLLECTION, PermissionGroup
    from db.persistence import get_repository, reset_repository_for_testing
    from db.repositories.memory import MemoryRepository
    from db.tenants import TenantConfig, TenantDirectory

    reset_repository_for_testing(MemoryRepository())
    repo = get_repository()
    ids = ["map-server", "map", "private", "global"]
    TenantDirectory(repo).put(TenantConfig(tenantId="tenant-a", enabledMcpServers=ids))
    repo.set_document(
        GROUP_COLLECTION,
        "maps",
        PermissionGroup(id="maps", tenantId="tenant-a", label="maps", mcpServers=ids).model_dump(by_alias=True),
    )
    for ref in ids:
        repo.set_document(
            "mcp_servers", ref, {"scope": "platform", "enabled": True, "url": "https://mcp.example.test/mcp"}
        )
    app = FastAPI()
    app.include_router(mcp_proxy.router)

    async def identity(request: Request):
        request.state.access = build_access_context(user)
        return user

    app.dependency_overrides[get_current_user] = identity
    root = RootAgentConfig(mcpServers=["map-server"])
    server = {
        "scope": "platform",
        "enabled": True,
        "url": "https://upstream.example.com/mcp",
        "headers": {"x-server-secret": "server-secret"},
    }
    monkeypatch.setattr(mcp_proxy, "get_platform_config", lambda: SimpleNamespace(agent=root))
    monkeypatch.setattr(mcp_proxy, "get_document", lambda *_: server)
    upstream = AsyncMock()
    upstream.request.return_value = httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": []}})
    context = AsyncMock()
    context.__aenter__.return_value = upstream
    monkeypatch.setattr(mcp_proxy.httpx, "AsyncClient", lambda **_: context)
    return TestClient(app), root, server, upstream


@pytest.mark.parametrize("method", ["POST", "GET", "DELETE"])
def test_authorized_methods_preserve_transport_and_strip_caller_secrets(setup, method):
    client, _, _, upstream = setup
    response = client.request(
        method,
        "/mcp/map-server",
        headers={"Authorization": "Bearer caller-secret", "Cookie": "private=value"},
        **({"json": {"jsonrpc": "2.0", "method": "tools/list"}} if method == "POST" else {}),
    )
    assert response.status_code == 200
    sent = upstream.request.call_args.kwargs
    assert sent["method"] == method
    assert sent["url"] == "https://upstream.example.com/mcp"
    assert sent["headers"]["x-server-secret"] == "server-secret"
    assert not {"authorization", "cookie"} & {key.lower() for key in sent["headers"]}


def test_empty_root_never_inherits_a_skill_binding(setup, monkeypatch):
    client, root, _, upstream = setup
    root.mcp_servers = []
    # 旧 Skill 即使仍含绑定, 代理也不会扫描它。
    monkeypatch.setattr("skills.skill_config.list_skills", lambda **_: pytest.fail("must not scan Skills"))
    assert client.post("/mcp/map-server", json={"method": "tools/list"}).status_code == 403
    upstream.request.assert_not_called()


def test_unbinding_takes_effect_on_next_request(setup):
    client, root, _, upstream = setup
    assert client.get("/mcp/map-server").status_code == 200
    root.mcp_servers.clear()
    assert client.get("/mcp/map-server").status_code == 403
    assert upstream.request.call_count == 1


def test_tenant_override_replaces_global_binding(setup):
    client, root, server, _ = setup
    from db.models.root_agent import RootAgentTenantOverride

    root.mcp_servers = ["global"]
    root.tenant_overrides = {"tenant-a": RootAgentTenantOverride(mcpServers=["private"])}
    server.update(scope="tenant", tenantId="tenant-a")
    assert client.get("/mcp/private").status_code == 200
    assert client.get("/mcp/global").status_code == 403


@pytest.mark.parametrize("fields", [{"enabled": False}, {"scope": "tenant", "tenantId": "tenant-b"}])
def test_disabled_or_foreign_server_is_invisible_even_when_bound(setup, fields):
    client, _, server, upstream = setup
    server.update(fields)
    assert client.get("/mcp/map-server").status_code == 404
    upstream.request.assert_not_called()


def test_unknown_server(setup, monkeypatch):
    client, _, _, upstream = setup
    monkeypatch.setattr(mcp_proxy, "get_document", lambda *_: None)
    assert client.get("/mcp/map-server").status_code == 404
    upstream.request.assert_not_called()


def test_server_credential_reference_is_resolved_and_missing_secret_blocks(setup, monkeypatch):
    client, _, server, upstream = setup
    server["headers"] = {"Authorization": "${MCP_TEST_CREDENTIAL}"}
    monkeypatch.setenv("MCP_TEST_CREDENTIAL", "Bearer upstream-secret")
    assert client.get("/mcp/map-server").status_code == 200
    assert upstream.request.call_args.kwargs["headers"]["Authorization"] == "Bearer upstream-secret"
    monkeypatch.delenv("MCP_TEST_CREDENTIAL")
    assert client.get("/mcp/map-server").status_code == 503
    assert upstream.request.call_count == 1


@pytest.mark.parametrize("status,expected", [(400, 400), (401, 401), (500, 502), (503, 502)])
def test_upstream_status(setup, status, expected):
    client, _, _, upstream = setup
    upstream.request.return_value = httpx.Response(status, content=b"upstream failure")
    assert client.get("/mcp/map-server").status_code == expected


@pytest.mark.parametrize(
    "exception,expected", [(httpx.ReadTimeout("timeout"), 504), (httpx.ConnectError("offline"), 502)]
)
def test_upstream_transport_failure(setup, exception, expected):
    client, _, _, upstream = setup
    upstream.request.side_effect = exception
    assert client.get("/mcp/map-server").status_code == expected


def test_tool_level_denial_is_preserved(setup, monkeypatch):
    client, _, _, upstream = setup
    monkeypatch.setattr(mcp_proxy, "mcp_call_allowed", lambda *_, **__: False)
    result = client.post("/mcp/map-server", json={"method": "tools/call", "params": {"name": "dangerous"}})
    assert result.status_code == 403
    upstream.request.assert_not_called()


def test_event_stream_content_type(setup):
    client, _, _, upstream = setup
    upstream.request.return_value = httpx.Response(
        200, content=b"event: message\ndata: {}\n\n", headers={"content-type": "text/event-stream"}
    )
    result = client.get("/mcp/map-server")
    assert result.headers["content-type"].startswith("text/event-stream")
    assert result.content == upstream.request.return_value.content
