"""真实持久化下验证权限组、Root、租户交集及管理边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from admin.access_routes import router as access_router
from admin.accounts_routes import router as accounts_router
from admin.groups_routes import router as groups_router
from admin.mcp_servers_routes import router as mcp_admin_router
from admin.tenants import router as tenants_router
from agents.routes import router as agent_router
from auth import User, get_current_user
from auth.access_context import build_access_context
from auth.capability_access import (
    GROUP_COLLECTION,
    PermissionGroup,
    authorized_root_config,
    refresh_authorization,
)
from auth.local_jwt import _user_doc_id, create_local_user, issue_access_token, user_from_token
from config.platform_config import invalidate_cache, update_platform_config
from db.models.root_agent import RootAgentConfig
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory
from protocols.mcp_proxy import router as proxy_router
from skills.skill_config import _cache, create_skill


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("AUTH_BACKEND", "local-jwt")
    monkeypatch.setenv("JWT_SIGNING_KEY", "isolated-signing-key-with-at-least-thirty-two-bytes")
    repository = MemoryRepository()
    reset_repository_for_testing(repository)
    invalidate_cache(clear_last_known_good=True)
    _cache.clear()
    skill = create_skill(
        name="lighting-analysis",
        description="照明分析",
        tenant_id="tenant-a",
        owner_id="owner",
        accessControl={"type": "public"},
    )
    private = create_skill(
        name="private-document",
        description="私有资料",
        tenant_id="tenant-a",
        owner_id="owner",
        accessControl={"type": "private"},
    )
    for tenant_id in ["tenant-a", "tenant-b"]:
        TenantDirectory(repository).put(
            TenantConfig(
                tenantId=tenant_id,
                enabledSkills=[skill.skill_id, private.skill_id],
                enabledMcpServers=["maps", "other"],
            )
        )
    for server_id in ["maps", "other"]:
        repository.set_document(
            "mcp_servers",
            server_id,
            {"scope": "tenant", "tenantId": "tenant-a", "enabled": True, "url": "https://mcp.example.test/mcp"},
        )
    root = RootAgentConfig(skills=[skill.skill_id, private.skill_id], mcpServers=["maps", "other"])
    update_platform_config({"agent": root.model_dump(by_alias=True)}, updated_by="admin")
    a = create_local_user(
        email="a@example.test", password="test-password-at-least-12", uid="same-uid", tenant_id="tenant-a"
    )
    b = create_local_user(
        email="b@example.test", password="test-password-at-least-12", uid="same-uid", tenant_id="tenant-b"
    )
    admin = User(uid="admin", tenant_id="tenant-a", group_tags=frozenset({"aitana-admin"}))

    def client(actor=admin):
        app = FastAPI()
        app.include_router(groups_router)
        app.include_router(tenants_router)
        app.include_router(mcp_admin_router, prefix="/api/admin")
        app.include_router(accounts_router, prefix="/api/admin")
        app.include_router(access_router)
        app.include_router(agent_router)
        app.include_router(proxy_router)

        async def identity(request: Request):
            user = refresh_authorization(actor)
            request.state.access = build_access_context(user)
            return user

        app.dependency_overrides[get_current_user] = identity
        return TestClient(app)

    def group(group_id, **fields):
        model = PermissionGroup(id=group_id, tenantId="tenant-a", label=group_id, **fields)
        repository.set_document(GROUP_COLLECTION, group_id, model.model_dump(by_alias=True))
        return model

    def assign(user, ids):
        repository.update_document("auth_users", _user_doc_id(user.email), {"permissionGroupIds": ids})

    yield SimpleNamespace(
        repo=repository,
        root=root,
        a=a,
        b=b,
        admin=admin,
        skill=skill,
        private=private,
        client=client,
        group=group,
        assign=assign,
    )
    _cache.clear()
    reset_repository_for_testing(None)
    invalidate_cache(clear_last_known_good=True)


def test_no_group_is_denied_and_union_is_narrowed_by_both_ceilings(setup):
    s = setup
    assert authorized_root_config(s.root, s.a).skills == []
    s.group("skills", skills=[s.skill.skill_id, s.private.skill_id])
    s.group("mcp", mcpServers=["maps", "other"])
    s.assign(s.a, ["skills", "mcp"])
    assert authorized_root_config(s.root, s.a).skills == [s.skill.skill_id]
    tenant = TenantDirectory(s.repo).get("tenant-a")
    TenantDirectory(s.repo).put(
        tenant.model_copy(update={"enabled_skills": [s.skill.skill_id], "enabled_mcp_servers": ["maps"]})
    )
    allowed = authorized_root_config(s.root, s.a)
    assert allowed.skills == [s.skill.skill_id]
    assert allowed.mcp_servers == ["maps"]
    assert authorized_root_config(RootAgentConfig(), s.a).mcp_servers == []
    assert authorized_root_config(RootAgentConfig(), s.a).skills == []


def test_tenant_private_override_replaces_global_and_preserves_acl(setup):
    s = setup
    from db.models.root_agent import RootAgentTenantOverride

    s.root.skills = ["global-only"]
    s.root.mcp_servers = ["global-only"]
    s.root.tenant_overrides = {
        "tenant-a": RootAgentTenantOverride(skills=[s.skill.skill_id, s.private.skill_id], mcpServers=["maps"])
    }
    update_platform_config({"agent": s.root.model_dump(by_alias=True)}, updated_by="admin")
    s.group("group", skills=[s.skill.skill_id, s.private.skill_id], mcpServers=["maps"])
    s.assign(s.a, ["group"])
    assert authorized_root_config(s.root, s.a).mcp_servers == ["maps"]
    preview = s.client().post("/api/admin/access/check", json={"email": s.a.email})
    assert preview.status_code == 200, preview.text
    assert preview.json()["skills"] == [{"id": s.skill.skill_id, "label": s.skill.name}]
    assert s.client(s.a).get(f"/api/agent/capabilities/{s.private.skill_id}").status_code == 404
    assert s.client(s.a).get(f"/api/agent/capabilities/{s.skill.skill_id}").status_code == 200


def test_membership_edit_is_exact_with_colliding_uids_and_refreshes_without_relogin(setup):
    s = setup
    s.group("group", skills=[s.skill.skill_id], mcpServers=["maps"])
    token, _ = issue_access_token(s.a)
    response = s.client().patch(
        f"/api/admin/accounts/{s.a.email}", json={"permission_group_ids": ["group"], "disabled": False}
    )
    assert response.status_code == 200, response.text
    assert authorized_root_config(s.root, user_from_token(token)).mcp_servers == ["maps"]
    assert authorized_root_config(s.root, s.b).mcp_servers == []
    assert s.repo.get_document("auth_users", _user_doc_id(s.b.email))["permissionGroupIds"] == []
    s.client().patch(f"/api/admin/accounts/{s.a.email}", json={"permission_group_ids": []})
    assert authorized_root_config(s.root, user_from_token(token)).mcp_servers == []


def test_foreign_group_and_server_cannot_grant_access(setup):
    s = setup
    s.group("group", skills=[s.skill.skill_id], mcpServers=["maps"])
    assert (
        s.client().patch(f"/api/admin/accounts/{s.b.email}", json={"permission_group_ids": ["group"]}).status_code
        == 422
    )
    s.assign(s.b, ["group"])
    assert authorized_root_config(s.root, s.b).skills == []
    assert authorized_root_config(s.root, s.b).mcp_servers == []


def test_group_delete_root_unbind_server_disable_and_account_disable_apply_immediately(setup):
    s = setup
    s.group("group", skills=[s.skill.skill_id], mcpServers=["maps"])
    s.assign(s.a, ["group"])
    assert authorized_root_config(s.root, s.a).mcp_servers == ["maps"]
    s.repo.update_document("mcp_servers", "maps", {"enabled": False})
    assert authorized_root_config(s.root, s.a).mcp_servers == []
    assert s.client().delete("/api/admin/groups/group").status_code == 204
    assert authorized_root_config(s.root, s.a).skills == []
    s.repo.update_document("auth_users", _user_doc_id(s.a.email), {"disabled": True})
    assert s.client(s.a).get("/api/agent").status_code == 403


def test_tenant_admin_is_derived_from_group_and_cannot_cross_scope_or_elevate(setup):
    s = setup
    s.group("admins", role="tenant-admin")
    s.assign(s.a, ["admins"])
    admin_client = s.client(s.a)
    assert admin_client.get("/api/admin/groups").status_code == 200
    assert admin_client.post("/api/admin/groups", json={"tenantId": "tenant-b", "label": "foreign"}).status_code == 403
    assert (
        admin_client.post(
            "/api/admin/groups", json={"tenantId": "tenant-a", "label": "super", "role": "platform-admin"}
        ).status_code
        == 422
    )
    assert (
        admin_client.post(
            "/api/admin/groups", json={"tenantId": "tenant-a", "label": "admin", "role": "tenant-admin"}
        ).status_code
        == 403
    )
    assert admin_client.patch(f"/api/admin/accounts/{s.b.email}", json={"permission_group_ids": []}).status_code == 403
    assert admin_client.delete("/api/admin/groups/admins").status_code == 403
    s.repo.delete_document(GROUP_COLLECTION, "admins")
    assert admin_client.get("/api/admin/groups").status_code == 403


def test_old_claim_roles_and_request_fields_do_not_grant_admin_authority(setup):
    s = setup
    s.repo.update_document("auth_users", _user_doc_id(s.a.email), {"groupTags": ["tenant-admin:tenant-a", "one-admin"]})
    assert s.client(s.a).get("/api/admin/groups").status_code == 403
    assert (
        s.client()
        .post("/api/admin/groups", json={"tenantId": "tenant-a", "label": "old", "grants": [s.skill.skill_id]})
        .status_code
        == 422
    )
    assert (
        s.client().patch(f"/api/admin/accounts/{s.a.email}", json={"group_tags": ["aitana-admin"]}).status_code == 422
    )


def test_group_can_only_select_resources_in_current_root_and_tenant(setup):
    s = setup
    payload = {"tenantId": "tenant-a", "label": "analysts", "skills": [s.skill.skill_id], "mcpServers": ["maps"]}
    result = s.client().post("/api/admin/groups", json=payload)
    assert result.status_code == 201, result.text
    assert result.json()["id"]
    assert s.client().post("/api/admin/groups", json={**payload, "mcpServers": ["not-bound"]}).status_code == 422
    assert (
        s.client().put(f"/api/admin/groups/{result.json()['id']}", json={**payload, "tenantId": "tenant-b"}).status_code
        == 422
    )


def test_runtime_metadata_never_exposes_ungranted_mcp_server(setup):
    s = setup
    s.group("group", mcpServers=["maps"])
    s.assign(s.a, ["group"])
    response = s.client(s.a).get("/api/agent")
    assert response.status_code == 200, response.text
    assert response.json()["skillMetadata"]["toolConfigs"]["mcp"] == {"servers": ["maps"]}
    s.assign(s.a, [])
    assert s.client(s.a).get("/api/agent").json()["skillMetadata"]["toolConfigs"]["mcp"] == {"servers": []}


def test_proxy_cannot_discover_or_call_ungranted_server(setup, monkeypatch):
    s = setup
    s.group("group", mcpServers=["maps"])
    s.assign(s.a, ["group"])
    from protocols import mcp_proxy

    client = s.client(s.a)
    upstream = AsyncMock()
    import httpx

    upstream.request.return_value = httpx.Response(200, json={"result": {}})
    context = AsyncMock()
    context.__aenter__.return_value = upstream
    monkeypatch.setattr(mcp_proxy.httpx, "AsyncClient", lambda **_: context)
    assert client.post("/mcp/other", json={"method": "tools/list"}).status_code == 403
    assert client.post("/mcp/other", json={"method": "tools/call", "params": {"name": "do"}}).status_code == 403
    upstream.request.assert_not_called()
    assert client.post("/mcp/maps", json={"method": "tools/call", "params": {"name": "do"}}).status_code == 200
    s.assign(s.a, [])
    assert client.post("/mcp/maps", json={"method": "tools/call", "params": {"name": "do"}}).status_code == 403
    assert upstream.request.call_count == 1


def test_disabled_tenant_revokes_management_and_runtime_access(setup):
    s = setup
    s.group("admins", role="tenant-admin", skills=[s.skill.skill_id], mcpServers=["maps"])
    s.assign(s.a, ["admins"])
    tenant = TenantDirectory(s.repo).get("tenant-a")
    TenantDirectory(s.repo).put(tenant.model_copy(update={"disabled": True}))
    assert s.client(s.a).get("/api/admin/groups").status_code == 403
    assert s.client(s.a).get("/api/agent").status_code == 403


@pytest.mark.parametrize("flag", ["allow_surface_context_writes", "allow_action_triggered_runs"])
def test_protocol_callbacks_use_current_group_and_root_policy(setup, flag):
    s = setup
    from datetime import UTC, datetime

    from fastapi import HTTPException

    from db.models.chat_session import ChatSessionIndex
    from protocols._a2ui_surface_shared import _enforce_root_interaction

    s.group("group", skills=[s.skill.skill_id])
    s.assign(s.a, ["group"])
    user = refresh_authorization(s.a)
    request = SimpleNamespace(state=SimpleNamespace(access=build_access_context(user)))
    now = datetime.now(UTC)
    index = ChatSessionIndex(
        sessionId="s",
        skillId=s.skill.skill_id,
        tenantId="tenant-a",
        ownerUid=user.uid,
        accessControl={"type": "private"},
        firstMessageAt=now,
        lastMessageAt=now,
    )
    with pytest.raises(HTTPException) as blocked:
        _enforce_root_interaction(index, user, request, flag)
    assert blocked.value.status_code == 403
    setattr(s.root.interaction, flag, True)
    update_platform_config({"agent": s.root.model_dump(by_alias=True)}, updated_by="admin")
    assert _enforce_root_interaction(index, user, request, flag).skill_id == s.skill.skill_id
    s.assign(s.a, [])
    with pytest.raises(HTTPException) as revoked:
        _enforce_root_interaction(index, user, request, flag)
    assert revoked.value.status_code == 403


def test_running_mcp_tool_rechecks_membership_before_invocation(setup):
    s = setup
    from adk.callbacks import make_permission_enforcer
    from auth.permissions import ToolPermissionDenied
    from tools.mcp.registry import SERVER_ID_ATTR

    s.group("group", mcpServers=["maps"])
    s.assign(s.a, ["group"])
    tool = SimpleNamespace(name="search_agent_knowledge", **{SERVER_ID_ATTR: "maps"})
    enforce = make_permission_enforcer(s.a.email, s.a.domain, user=s.a, root_agent=True)
    context = SimpleNamespace(agent_name="root")
    assert enforce(tool, {}, context) is None
    s.assign(s.a, [])
    with pytest.raises(ToolPermissionDenied):
        enforce(tool, {}, context)


def test_tenant_allowlists_reject_foreign_resources_and_retired_fields(setup):
    s = setup
    c = s.client()
    assert c.patch("/api/admin/tenants/tenant-b", json={"enabled_skills": [s.skill.skill_id]}).status_code == 422
    assert c.patch("/api/admin/tenants/tenant-b", json={"enabled_mcp_servers": ["maps"]}).status_code == 422
    assert c.patch("/api/admin/tenants/tenant-a", json={"derived_group_tags": ["aitana-admin"]}).status_code == 422
    assert (
        c.patch(
            "/api/admin/tenants/tenant-a", json={"enabled_skills": [s.skill.skill_id], "enabled_mcp_servers": ["maps"]}
        ).status_code
        == 200
    )


def test_isolation_acceptance_fixture_uses_real_groups_and_cleans_them(setup, monkeypatch):
    from admin.scope import resolve_admin_scope
    from auth.local_jwt import authenticate_credentials
    from scripts import seed_tenant_acceptance as acceptance

    s = setup
    monkeypatch.setenv("TENANT_E2E_PASSWORD_A", "isolated-acceptance-password-a")
    monkeypatch.setenv("TENANT_E2E_PASSWORD_B", "isolated-acceptance-password-b")
    monkeypatch.setattr(acceptance, "_model_pair", lambda: ("model-a", "model-b"))
    ids = acceptance.seed("permission-groups")
    user = refresh_authorization(authenticate_credentials(ids["email_a"], "isolated-acceptance-password-a"))
    scope = resolve_admin_scope(user)
    assert scope.may_tenant(ids["tenant_a"])
    assert not scope.may_tenant(ids["tenant_b"])
    assert user.permission_group_ids == frozenset({ids["group_a"]})
    acceptance.cleanup("permission-groups")
    assert s.repo.get_document(GROUP_COLLECTION, ids["group_a"]) is None
    assert s.repo.get_document(GROUP_COLLECTION, ids["group_b"]) is None


def test_case_distinct_tenants_do_not_share_admin_mcp_or_audit_scope(setup):
    s = setup
    TenantDirectory(s.repo).put(TenantConfig(tenantId="Tenant-A"))
    group = PermissionGroup(id="case-admins", tenantId="Tenant-A", label="case admin", role="tenant-admin")
    s.repo.set_document(GROUP_COLLECTION, group.id, group.model_dump(by_alias=True))
    actor = create_local_user(
        email="case@example.test",
        password="isolated-case-password",
        tenant_id="Tenant-A",
        permission_group_ids=[group.id],
    )
    c = s.client(actor)
    body = {"url": "https://example.test/mcp", "scope": "tenant", "tenant_id": "Tenant-A"}
    created = c.put("/api/admin/mcp-servers/case-server", json=body)
    assert created.status_code == 200, created.text
    assert created.json()["tenant_id"] == "Tenant-A"
    assert s.repo.get_document("mcp_servers", "case-server")["tenantId"] == "Tenant-A"
    assert c.put("/api/admin/mcp-servers/other-case", json={**body, "tenant_id": "tenant-a"}).status_code == 403
    rows = s.repo.query_documents("admin_audit", limit=None)
    assert any(row.get("tenantId") == "Tenant-A" and row.get("actorTenantId") == "Tenant-A" for row in rows)


def test_explicit_specialist_cannot_restore_its_own_native_tools(setup):
    s = setup
    from adk.agent import create_agent
    from agents.root_runtime import compose_root_skill, root_agent_skill

    child = create_skill(
        name="specialist",
        description="Specialist capability",
        tenant_id="tenant-a",
        owner_id="owner",
        accessControl={"type": "public"},
        skillMetadata={"tools": ["unbound_nonexistent_tool"]},
    )
    tenant = TenantDirectory(s.repo).get("tenant-a")
    TenantDirectory(s.repo).put(tenant.model_copy(update={"enabled_skills": [child.skill_id]}))
    s.root.skills = [child.skill_id]
    s.root.specialist_agents = [child.skill_id]
    s.root.mcp_servers = []
    s.root.tools = []
    update_platform_config({"agent": s.root.model_dump(by_alias=True)}, updated_by="admin")
    s.group("group", skills=[child.skill_id])
    s.assign(s.a, ["group"])
    user = refresh_authorization(s.a)
    policy = authorized_root_config(s.root, user)
    runtime = compose_root_skill(root_agent_skill(policy), policy)
    agent = create_agent(runtime, user, access_context=build_access_context(user))
    assert len(agent.sub_agents) == 1
    assert "unbound_nonexistent_tool" not in [getattr(tool, "name", "") for tool in agent.sub_agents[0].tools]


def test_group_identifier_cannot_mint_a_protected_admin_role(setup):
    s = setup
    s.group("aitana-admin")
    s.assign(s.a, ["aitana-admin"])
    assert "aitana-admin" not in refresh_authorization(s.a).group_tags
    assert s.client(s.a).get("/api/admin/groups").status_code == 403
