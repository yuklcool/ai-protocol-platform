"""Regression tests for the MCP Server administrative enabled switch."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

_PLATFORM_ADMIN = User(
    uid="platform-admin",
    email="owner@platform.test",
    domain="platform.test",
    tenant_id="platform",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT_USER = User(
    uid="tenant-user",
    email="user@example.com",
    domain="example.com",
    tenant_id="tenant-a",
)


def _admin_client() -> TestClient:
    from admin.routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return _PLATFORM_ADMIN

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


def _proxy_client() -> TestClient:
    from protocols.mcp_proxy import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _TENANT_USER
    return TestClient(app)


def test_admin_can_persist_disabled_server() -> None:
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=None),
        patch("admin.mcp_servers_routes.set_document") as write,
        patch("admin.mcp_servers_routes.clear_registry_cache"),
        patch("admin.mcp_servers_routes.record_admin_action"),
    ):
        response = _admin_client().put(
            "/api/admin/mcp-servers/shared-map",
            json={
                "url": "http://mcp-example-map:8080/mcp",
                "transport": "streamable-http",
                "scope": "platform",
                "enabled": False,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    written = write.call_args.args[2]
    assert written["enabled"] is False


def test_admin_legacy_row_without_enabled_is_reported_enabled() -> None:
    legacy = {
        "url": "https://mcp.example.test/mcp",
        "transport": "http",
        "scope": "platform",
    }
    with patch("admin.mcp_servers_routes.get_document", return_value=legacy):
        response = _admin_client().get("/api/admin/mcp-servers/legacy")

    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_disabled_server_is_hidden_from_runtime_proxy() -> None:
    disabled = {
        "url": "https://mcp.example.test/mcp",
        "transport": "http",
        "scope": "platform",
        "enabled": False,
    }
    with patch("protocols.mcp_proxy.get_document", return_value=disabled):
        response = _proxy_client().post(
            "/mcp/shared-map",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 404
