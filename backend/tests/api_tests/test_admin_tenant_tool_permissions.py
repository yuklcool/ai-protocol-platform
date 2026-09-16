"""Admin authorization tests for first-class tenant tool permissions."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

_PLATFORM = User(
    uid="platform",
    email="platform@example.net",
    domain="example.net",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT_A = User(
    uid="admin-a",
    email="admin@a.example",
    domain="a.example",
    tenant_id="tenant-a",
    group_tags=frozenset({"tenant-admin:tenant-a"}),
)


def _client(user: User) -> TestClient:
    from admin.tool_permissions_routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


def test_tenant_admin_can_manage_own_first_class_rule() -> None:
    with (
        patch("admin.tool_permissions_routes.get_document", return_value=None),
        patch("admin.tool_permissions_routes.set_document") as write,
        patch("admin.tool_permissions_routes.perms.clear_cache"),
        patch("admin.tool_permissions_routes.record_admin_action") as audit,
    ):
        response = _client(_TENANT_A).put(
            "/api/admin/tool-permissions/tenant:tenant-a",
            json={"type": "tenant", "tools": ["search"], "denied": []},
        )

    assert response.status_code == 200, response.text
    assert response.json()["tenantId"] == "tenant-a"
    write.assert_called_once_with(
        "tool_permissions",
        "tenant:tenant-a",
        {"type": "tenant", "tools": ["search"], "denied": [], "tenantId": "tenant-a"},
    )
    assert audit.call_args.kwargs["tenant_id"] == "tenant-a"


def test_tenant_admin_cannot_manage_other_tenant_rule() -> None:
    with patch("admin.tool_permissions_routes.get_document", return_value=None):
        response = _client(_TENANT_A).put(
            "/api/admin/tool-permissions/tenant:tenant-b",
            json={"type": "tenant", "tools": ["search"], "denied": []},
        )
    assert response.status_code == 403


def test_tenant_admin_list_only_returns_trusted_owned_rows() -> None:
    rows = [
        {"__id": "tenant:tenant-a", "type": "tenant", "tenantId": "tenant-a", "tools": ["search"]},
        {"__id": "tenant:tenant-b", "type": "tenant", "tenantId": "tenant-b", "tools": ["billing"]},
        {"__id": "legacy@example.com", "type": "user", "tools": ["legacy"]},
        {"__id": "*", "type": "wildcard", "tools": ["*"]},
    ]
    with (
        patch("admin.tool_permissions_routes.query_documents", return_value=rows),
        patch("admin.tool_permissions_routes.get_local_user_by_email", return_value=None),
    ):
        response = _client(_TENANT_A).get("/api/admin/tool-permissions")

    assert response.status_code == 200
    assert [row["doc_id"] for row in response.json()] == ["tenant:tenant-a"]


def test_mapped_legacy_domain_rule_is_visible_to_stable_tenant_admin() -> None:
    row = {"type": "domain", "tools": ["search"], "denied": []}
    with (
        patch("admin.tool_permissions_routes.get_document", return_value=row),
        patch("admin.tool_permissions_routes.tenant_id_for_domain", return_value="tenant-a"),
    ):
        response = _client(_TENANT_A).get("/api/admin/tool-permissions/a.example")

    assert response.status_code == 200, response.text
    assert response.json()["tenantId"] == "tenant-a"


def test_unowned_user_rule_stays_platform_only() -> None:
    row = {"type": "user", "tools": ["search"], "denied": []}
    with (
        patch("admin.tool_permissions_routes.get_document", return_value=row),
        patch("admin.tool_permissions_routes.get_local_user_by_email", return_value=None),
    ):
        tenant_response = _client(_TENANT_A).get("/api/admin/tool-permissions/user@a.example")
        platform_response = _client(_PLATFORM).get("/api/admin/tool-permissions/user@a.example")

    assert tenant_response.status_code == 403
    assert platform_response.status_code == 200
    assert platform_response.json()["tenantId"] is None


def test_exact_local_user_assignment_is_trusted_for_user_rule() -> None:
    row = {"type": "user", "tools": ["search"], "denied": []}
    local_user = {"email": "user@any.example", "tenantId": "tenant-a"}
    with (
        patch("admin.tool_permissions_routes.get_document", return_value=row),
        patch("admin.tool_permissions_routes.get_local_user_by_email", return_value=local_user),
    ):
        response = _client(_TENANT_A).get("/api/admin/tool-permissions/user@any.example")

    assert response.status_code == 200
    assert response.json()["tenantId"] == "tenant-a"


def test_permission_type_and_key_must_match() -> None:
    response = _client(_PLATFORM).put(
        "/api/admin/tool-permissions/tenant:tenant-a",
        json={"type": "domain", "tools": []},
    )
    assert response.status_code == 422
