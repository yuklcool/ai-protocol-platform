"""API tests for the MCP Server admin control plane (issue #11)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

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


def test_list_redacts_header_values(platform_admin: TestClient) -> None:
    rows = [
        {
            "__id": "private-api",
            "url": "http://mcp-api:8080/mcp",
            "transport": "streamable-http",
            "scope": "tenant",
            "tenantId": "a.com",
            "headers": {"Authorization": "Bearer super-secret", "X-Key": "${MCP_KEY}"},
        }
    ]
    with patch("admin.mcp_servers_routes.query_documents", return_value=rows):
        response = platform_admin.get("/api/admin/mcp-servers")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["header_names"] == ["Authorization", "X-Key"]
    assert body["has_credentials"] is True
    assert "headers" not in body
    assert "super-secret" not in response.text
    assert "${MCP_KEY}" not in response.text


def test_tenant_list_sees_platform_and_own_private_only(tenant_admin: TestClient) -> None:
    rows = [
        {"__id": "shared", "url": "https://shared.test/mcp", "scope": "platform"},
        {"__id": "mine", "url": "https://mine.test/mcp", "scope": "tenant", "tenantId": "a.com"},
        {"__id": "foreign", "url": "https://foreign.test/mcp", "scope": "tenant", "tenantId": "b.com"},
        {"__id": "legacy", "url": "https://legacy.test/mcp"},
    ]
    with patch("admin.mcp_servers_routes.query_documents", return_value=rows):
        response = tenant_admin.get("/api/admin/mcp-servers")

    assert response.status_code == 200
    assert [row["server_id"] for row in response.json()] == ["mine", "shared"]


def test_tenant_can_create_own_server_and_docker_service_url(tenant_admin: TestClient) -> None:
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=None),
        patch("admin.mcp_servers_routes.set_document") as write,
        patch("admin.mcp_servers_routes.clear_registry_cache") as clear_cache,
        patch("admin.mcp_servers_routes.record_admin_action"),
    ):
        response = tenant_admin.put(
            "/api/admin/mcp-servers/local-tools",
            json={
                "url": "http://mcp-sandbox:8080/mcp",
                "transport": "streamable-http",
                "scope": "tenant",
                "headers": {"Authorization": "${MCP_SANDBOX_TOKEN}"},
            },
        )

    assert response.status_code == 200
    written = write.call_args.args[2]
    assert written["tenantId"] == "a.com"
    assert written["url"] == "http://mcp-sandbox:8080/mcp"
    assert written["headers"]["Authorization"] == "${MCP_SANDBOX_TOKEN}"
    assert "headers" not in response.json()
    clear_cache.assert_called_once_with()


def test_tenant_cannot_create_platform_server(tenant_admin: TestClient) -> None:
    with patch("admin.mcp_servers_routes.set_document") as write:
        response = tenant_admin.put(
            "/api/admin/mcp-servers/shared",
            json={"url": "https://shared.test/mcp", "scope": "platform"},
        )
    assert response.status_code == 403
    write.assert_not_called()


def test_tenant_cannot_overwrite_foreign_server(tenant_admin: TestClient) -> None:
    existing = {
        "url": "https://foreign.test/mcp",
        "scope": "tenant",
        "tenantId": "b.com",
    }
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=existing),
        patch("admin.mcp_servers_routes.set_document") as write,
    ):
        response = tenant_admin.put(
            "/api/admin/mcp-servers/foreign",
            json={"url": "https://mine.test/mcp", "scope": "tenant"},
        )
    assert response.status_code == 403
    write.assert_not_called()


def test_audit_snapshot_never_contains_header_values(platform_admin: TestClient) -> None:
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=None),
        patch("admin.mcp_servers_routes.set_document"),
        patch("admin.mcp_servers_routes.clear_registry_cache"),
        patch("admin.mcp_servers_routes.record_admin_action") as audit,
    ):
        response = platform_admin.put(
            "/api/admin/mcp-servers/shared",
            json={
                "url": "https://shared.test/mcp",
                "scope": "platform",
                "headers": {"Authorization": "Bearer do-not-log"},
            },
        )

    assert response.status_code == 200
    audited = audit.call_args.kwargs["after"]
    assert "headers" not in audited
    assert audited["headerNames"] == ["Authorization"]
    assert "do-not-log" not in repr(audit.call_args)


def test_omitted_headers_preserve_existing_credentials(platform_admin: TestClient) -> None:
    existing = {
        "url": "https://shared.test/old",
        "scope": "platform",
        "headers": {"Authorization": "${SHARED_MCP_TOKEN}"},
    }
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=existing),
        patch("admin.mcp_servers_routes.set_document") as write,
        patch("admin.mcp_servers_routes.clear_registry_cache"),
        patch("admin.mcp_servers_routes.record_admin_action"),
    ):
        response = platform_admin.put(
            "/api/admin/mcp-servers/shared",
            json={"url": "https://shared.test/new", "scope": "platform"},
        )

    assert response.status_code == 200
    assert write.call_args.args[2]["headers"] == {"Authorization": "${SHARED_MCP_TOKEN}"}


def test_delete_clears_runtime_registry_cache(platform_admin: TestClient) -> None:
    existing = {"url": "https://shared.test/mcp", "scope": "platform"}
    with (
        patch("admin.mcp_servers_routes.get_document", return_value=existing),
        patch("admin.mcp_servers_routes.delete_document") as delete,
        patch("admin.mcp_servers_routes.clear_registry_cache") as clear_cache,
        patch("admin.mcp_servers_routes.record_admin_action"),
    ):
        response = platform_admin.delete("/api/admin/mcp-servers/shared")

    assert response.status_code == 200
    delete.assert_called_once_with("mcp_servers", "shared")
    clear_cache.assert_called_once_with()
