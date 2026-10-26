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
            json={
                "url": "https://shared.test/new",
            },
        )

    assert response.status_code == 200
    assert write.call_args.args[2]["headers"] == {"Authorization": "${SHARED_MCP_TOKEN}"}


def test_account_scope_is_saved_and_omission_keeps_restrictions(platform_admin: TestClient) -> None:
    for body, expected in [
        ({"allowedUserIds": ["owner", "owner"]}, ["owner"]),
        ({}, ["owner"]),
        ({"allowedUserIds": []}, []),
    ]:
        with (
            patch(
                "admin.mcp_servers_routes.get_document",
                return_value={"url": "http://lighting/mcp", "allowedUserIds": ["owner"]},
            ),
            patch("admin.mcp_servers_routes.set_document") as write,
            patch("admin.mcp_servers_routes.clear_registry_cache"),
            patch("admin.mcp_servers_routes.record_admin_action"),
        ):
            response = platform_admin.put("/api/admin/mcp-servers/lighting", json={"url": "http://lighting/mcp", **body})
        assert response.status_code == 200
        assert response.json()["allowedUserIds"] == expected
        assert write.call_args.args[2]["allowedUserIds"] == expected


def test_delete_clears_runtime_registry_cache(platform_admin: TestClient) -> None:
    existing = {
        "url": "https://shared.test/mcp",
    }
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
