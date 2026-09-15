"""API tests for MCP health and capability discovery admin endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from tools.mcp.diagnostics import McpDiagnosticError

_PLATFORM_ADMIN = User(
    uid="platform-admin",
    email="owner@platform.test",
    domain="platform.test",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT_ADMIN = User(
    uid="tenant-a-admin",
    email="ops@a.com",
    domain="a.com",
    group_tags=frozenset({"tenant-admin:a.com"}),
)


def _client(user: User) -> TestClient:
    from admin.routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


@pytest.fixture()
def platform_admin() -> TestClient:
    return _client(_PLATFORM_ADMIN)


@pytest.fixture()
def tenant_admin() -> TestClient:
    return _client(_TENANT_ADMIN)


def test_health_runs_real_diagnostic_boundary_for_visible_server(tenant_admin: TestClient) -> None:
    config = {
        "url": "http://mcp-sandbox:8080/mcp",
        "transport": "streamable-http",
        "scope": "tenant",
        "tenantId": "a.com",
        "headers": {"Authorization": "${MCP_TOKEN}"},
    }
    diagnostic = AsyncMock(
        return_value={
            "ok": True,
            "server": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "sandbox"}},
        }
    )
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=config),
        patch("admin.mcp_servers_routes.check_mcp_server", diagnostic),
    ):
        response = tenant_admin.post("/api/admin/mcp-servers/sandbox/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["server"]["serverInfo"]["name"] == "sandbox"
    diagnostic.assert_awaited_once_with("sandbox", config)
    assert "MCP_TOKEN" not in response.text
    assert "Authorization" not in response.text


def test_health_returns_structured_authentication_failure(platform_admin: TestClient) -> None:
    config = {"url": "https://mcp.example.test/mcp", "scope": "platform"}
    diagnostic = AsyncMock(side_effect=McpDiagnosticError("authentication", "401 Unauthorized"))
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=config),
        patch("admin.mcp_servers_routes.check_mcp_server", diagnostic),
    ):
        response = platform_admin.post("/api/admin/mcp-servers/shared/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "category": "authentication",
        "message": "401 Unauthorized",
        "server": None,
    }


def test_tenant_cannot_probe_foreign_private_server(tenant_admin: TestClient) -> None:
    config = {
        "url": "https://foreign.example.test/mcp",
        "scope": "tenant",
        "tenantId": "b.com",
    }
    diagnostic = AsyncMock()
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=config),
        patch("admin.mcp_servers_routes.check_mcp_server", diagnostic),
    ):
        response = tenant_admin.post("/api/admin/mcp-servers/foreign/health")

    assert response.status_code == 404
    diagnostic.assert_not_awaited()


def test_discover_returns_tools_resources_prompts_and_mcp_apps(platform_admin: TestClient) -> None:
    config = {"url": "https://mcp.example.test/mcp", "scope": "platform"}
    diagnostic = AsyncMock(
        return_value={
            "ok": True,
            "server": {"protocolVersion": "2025-06-18"},
            "tools": [{"name": "show_map"}],
            "resources": [{"uri": "ui://maps/result", "mimeType": "text/html;profile=mcp-app"}],
            "prompts": [{"name": "map_prompt"}],
            "warnings": [
                {"capability": "prompts", "category": "protocol", "message": "method unsupported"}
            ],
            "mcpApps": {"supported": True, "resourceUris": ["ui://maps/result"]},
        }
    )
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=config),
        patch("admin.mcp_servers_routes.discover_mcp_server", diagnostic),
    ):
        response = platform_admin.post("/api/admin/mcp-servers/shared/discover")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["tools"] == [{"name": "show_map"}]
    assert body["resources"][0]["uri"] == "ui://maps/result"
    assert body["prompts"] == [{"name": "map_prompt"}]
    assert body["mcp_apps"] == {"supported": True, "resourceUris": ["ui://maps/result"]}
    assert body["warnings"][0]["capability"] == "prompts"


def test_discover_returns_schema_failure_without_leaking_config(platform_admin: TestClient) -> None:
    config = {
        "url": "https://mcp.example.test/mcp",
        "scope": "platform",
        "headers": {"Authorization": "Bearer super-secret"},
    }
    diagnostic = AsyncMock(side_effect=McpDiagnosticError("schema", "tools/list returned an invalid schema"))
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=config),
        patch("admin.mcp_servers_routes.discover_mcp_server", diagnostic),
    ):
        response = platform_admin.post("/api/admin/mcp-servers/shared/discover")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["category"] == "schema"
    assert "super-secret" not in response.text
    assert "Authorization" not in response.text
