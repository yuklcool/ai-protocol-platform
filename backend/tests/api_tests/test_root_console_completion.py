"""Root console operations against isolated in-memory persistence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from auth.access_context import build_access_context
from auth.local_jwt import create_local_user, issue_access_token, user_from_token
from config.platform_config import invalidate_cache, update_platform_config
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory

ADMIN = User(uid="admin", email="admin@local.test", tenant_id="tenant-a", group_tags=frozenset({"aitana-admin"}))
A = User(uid="shared", email="a@local.test", tenant_id="tenant-a")
B = User(uid="shared", email="b@local.test", tenant_id="tenant-b")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("LOCAL_MODE", "1")
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("AUTH_BACKEND", "local-jwt")
    monkeypatch.setenv("JWT_SIGNING_KEY", "isolated-test-signing-key-that-is-not-a-real-secret")
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    invalidate_cache(clear_last_known_good=True)
    for name in ("tenant-a", "tenant-b"):
        TenantDirectory(repo).put(TenantConfig(tenantId=name, displayName=name, quota={"llmBudgetUsd": 1}))
    yield repo
    reset_repository_for_testing(None)
    invalidate_cache(clear_last_known_good=True)


def client(user=ADMIN):
    from admin.access_routes import router as access
    from admin.routes import router as admin
    from admin.tenants import router as tenants
    from agents.knowledge import router as knowledge
    from protocols.voice_routes import router as voice

    app = FastAPI()
    app.include_router(admin)
    app.include_router(tenants)
    app.include_router(access)
    app.include_router(knowledge)
    app.include_router(voice)

    async def identity(request: Request):
        request.state.access = build_access_context(user)
        return user

    app.dependency_overrides[get_current_user] = identity
    return TestClient(app)


def test_local_account_lifecycle_revokes_old_tokens_without_auditing_passwords(isolated):
    c = client()
    with patch("admin.accounts_routes.record_admin_action") as audit:
        response = c.post(
            "/api/admin/accounts",
            json={"email": "member@local.test", "password": "temporary-test-password-1", "tenant_id": "tenant-a"},
        )
        assert response.status_code == 201, response.text
        assert "password" not in response.text.lower()
        user = create_local_user(email="other@local.test", password="temporary-test-password-2", tenant_id="tenant-b")
        token, _ = issue_access_token(user)
        assert user_from_token(token).tenant_id == "tenant-b"
        reset = c.post(
            "/api/admin/accounts/other@local.test/password", json={"password": "replacement-test-password-3"}
        )
        assert reset.status_code == 200
        with pytest.raises(jwt.InvalidTokenError):
            user_from_token(token)
        for call in audit.call_args_list:
            assert "passwordHash" not in str(call.kwargs)
            assert "temporary-test-password" not in str(call.kwargs)
        assert c.patch("/api/admin/accounts/member@local.test", json={"disabled": True}).status_code == 200
        assert c.get("/api/admin/accounts").json()[0]["disabled"] is True
    assert client(A).get("/api/admin/accounts").status_code == 403
    assert (
        c.post(
            "/api/admin/accounts",
            json={"email": "x@local.test", "password": "temporary-test-password-1", "tenant_id": "missing"},
        ).status_code
        == 422
    )


def test_knowledge_grants_remain_tenant_scoped_and_revocation_is_immediate(isolated):
    from agents.knowledge import search_sources

    isolated.set_document(
        "parsed_documents",
        "document-a",
        {
            "tenantId": "tenant-a",
            "userId": ADMIN.uid,
            "originalFilename": "照明规范.txt",
            "parseStatus": "parsed",
            "text": "道路照明节能要求: 支路按车流量调光。",
        },
    )
    c = client()
    with patch("agents.knowledge.record_admin_action"):
        private = c.post("/api/agent/knowledge/sources", json={"document_id": "document-a"}).json()
        shared = c.post("/api/agent/knowledge/sources", json={"document_id": "document-a", "sharing": "tenant"}).json()
        assert search_sources([private["id"]], "照明", build_access_context(A))["results"] == []
        result = search_sources([shared["id"]], "照明节能", build_access_context(A))
        assert result["results"][0]["source"] == "照明规范.txt"
        assert "车流量" in result["results"][0]["excerpt"]
        assert search_sources([shared["id"]], "照明", build_access_context(B))["results"] == []
        assert c.delete(f"/api/agent/knowledge/sources/{shared['id']}").status_code == 204
        assert search_sources([shared["id"]], "照明", build_access_context(A))["results"] == []
    isolated.set_document(
        "parsed_documents",
        "other",
        {"tenantId": "tenant-b", "userId": ADMIN.uid, "parseStatus": "parsed", "text": "foreign"},
    )
    assert c.post("/api/agent/knowledge/sources", json={"document_id": "other", "sharing": "tenant"}).status_code == 404
    isolated.set_document(
        "parsed_documents", "pending", {"tenantId": "tenant-a", "userId": ADMIN.uid, "parseStatus": "pending"}
    )
    assert c.post("/api/agent/knowledge/sources", json={"document_id": "pending"}).status_code == 422


def test_domainless_tenant_and_root_overrides_preserve_global_policy(isolated):
    c = client()
    with patch("admin.tenants.record_admin_action"), patch("admin.tenant_root_routes.record_admin_action"):
        created = c.post("/api/admin/tenants", json={"tenant_id": "domainless", "display_name": "No domain"})
        assert created.status_code == 201, created.text
        assert created.json()["config"]["domains"] == []
        update_platform_config(
            {"agent": {"model": "smart", "tenantOverrides": {"tenant-b": {"budgetEnabled": True}}}},
            updated_by=ADMIN.uid,
        )
        saved = c.put("/api/admin/tenant-root/tenant-a", json={"override": {"budgetEnabled": True, "tools": []}})
        assert saved.status_code == 200, saved.text
        assert saved.json()["effective"]["budgetEnabled"] is True
        from config.platform_config import get_platform_config

        assert get_platform_config().agent.tenant_overrides["tenant-b"].budget_enabled is True
    tenant_admin = A.model_copy(update={"group_tags": frozenset({"tenant-admin:tenant-a"})})
    assert [row["tenantId"] for row in client(tenant_admin).get("/api/admin/tenants").json()] == ["tenant-a"]
    assert (
        client(tenant_admin).patch("/api/admin/tenants/tenant-a", json={"quota": {"llmBudgetUsd": 999}}).status_code
        == 403
    )
    assert c.patch("/api/admin/tenants/tenant-a", json={"quota": {"llmBudgetUsd": -1}}).status_code == 422


def test_root_voice_off_rejects_synthesis_and_on_uses_browser(isolated):
    c = client()
    update_platform_config({"agent": {"interaction": {"voiceEnabled": False}}}, updated_by=ADMIN.uid)
    assert c.get("/api/voice/config?skill_id=root-agent").json()["tts"]["enabled"] is False
    assert c.post("/api/voice/tts/synthesize", json={"skill_id": "root-agent", "text": "hello"}).status_code == 403
    update_platform_config({"agent": {"interaction": {"voiceEnabled": True}}}, updated_by=ADMIN.uid)
    config = c.get("/api/voice/config?skill_id=root-agent").json()["tts"]
    assert config["enabled"] is True
    assert config["provider"] == "browser"


@pytest.mark.asyncio
async def test_usage_persists_final_response_once_and_isolates_same_uid(isolated):
    from observability.usage import COLLECTION, make_usage_callbacks

    for user in (A, B):
        before, after = make_usage_callbacks(user, "root-agent")
        context = SimpleNamespace(invocation_id="invocation")
        request = SimpleNamespace(model="openai/gpt-5.6-luna")
        final = SimpleNamespace(
            partial=False, usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
        )
        await before(context, request)
        await after(context, SimpleNamespace(partial=True))
        await after(context, final)
        await after(context, final)
    assert len(isolated.query_documents(COLLECTION)) == 2
    tenant_admin = A.model_copy(update={"group_tags": frozenset({"tenant-admin:tenant-a"})})
    summary = client(tenant_admin).get("/api/admin/usage").json()
    assert summary["totals"]["calls"] == 1
    assert summary["totals"]["inputTokens"] == 100
    assert summary["totals"]["estimatedCostUsd"] > 0
    assert [row["tenantId"] for row in summary["tenants"]] == ["tenant-a"]
    assert client(tenant_admin).get("/api/admin/usage?tenant_id=tenant-b").status_code == 403


def test_root_budget_overrides_capability_exemption(isolated):
    from agents.root_runtime import compose_root_skill, root_agent_skill
    from db.models.root_agent import RootAgentConfig

    config = RootAgentConfig(budgetEnabled=True)
    skill = root_agent_skill(config)
    skill.skill_metadata.tool_configs = {"budget": {"exempt": True, "identity_key": "uid"}}
    composed = compose_root_skill(skill, config)
    assert composed.skill_metadata.tool_configs["budget"] == {
        "identity_key": "tenant_id",
        "missing_identity_policy": "block",
    }
    assert composed.skill_metadata.tool_configs["root_agent"]["budget_enabled"] is True


def test_disable_account_in_disabled_tenant_with_same_uid_as_actor(isolated):
    create_local_user(email=ADMIN.email, password="temporary-test-password-1", tenant_id="tenant-a", uid=ADMIN.uid)
    create_local_user(email=B.email, password="temporary-test-password-1", tenant_id="tenant-b", uid=ADMIN.uid)
    TenantDirectory(isolated).put(TenantConfig(tenantId="tenant-b", disabled=True))
    assert (
        client().patch(f"/api/admin/accounts/{B.email}", json={"tenant_id": "tenant-b", "disabled": True}).status_code
        == 200
    )
    assert client().patch(f"/api/admin/accounts/{ADMIN.email}", json={"disabled": True}).status_code == 422


def test_knowledge_sharing_changes_apply_to_existing_bindings(isolated):
    from agents.knowledge import search_sources

    isolated.set_document(
        "parsed_documents",
        "grant",
        {"tenantId": "tenant-a", "userId": ADMIN.uid, "parseStatus": "parsed", "text": "lighting policy"},
    )
    c = client()
    source = c.post("/api/agent/knowledge/sources", json={"document_id": "grant", "sharing": "tenant"}).json()
    assert search_sources([source["id"]], "lighting", build_access_context(A))["results"]
    response = c.patch(f"/api/agent/knowledge/sources/{source['id']}", json={"sharing": "private", "label": "Policy"})
    assert response.status_code == 200, response.text
    assert not search_sources([source["id"]], "lighting", build_access_context(A))["results"]


def test_remote_tool_cannot_impersonate_trusted_knowledge_tool(isolated):
    from adk.callbacks import make_permission_enforcer
    from agents.knowledge import knowledge_tool
    from auth.permissions import ToolPermissionDenied

    enforce = make_permission_enforcer(A.email, "local.test", user=A, root_agent=False)
    with patch("adk.callbacks.can_use_tool", return_value=False):
        assert enforce(knowledge_tool([], build_access_context(A)), {}, SimpleNamespace(agent_name="root")) is None
        with pytest.raises(ToolPermissionDenied):
            enforce(SimpleNamespace(name="search_agent_knowledge"), {}, SimpleNamespace(agent_name="root"))


def test_dynamic_model_prices_require_pair_and_drive_estimates(isolated):
    from observability.llm_metrics import estimate_cost, pricing_for_model

    c = client()
    provider = c.put(
        "/api/admin/model-providers/custom",
        json={
            "name": "Local test",
            "kind": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "api_key_ref": "${OPENAI_API_KEY}",
            "enabled": True,
        },
    )
    assert provider.status_code == 200, provider.text
    model = {
        "api_name": "unknown-test-model",
        "provider_id": "custom",
        "context_window": 16000,
        "max_output_tokens": 1024,
        "input_cost_per_million": 2,
        "output_cost_per_million": 6,
    }
    saved = c.put("/api/admin/model-providers/models/custom-model", json=model)
    assert saved.status_code == 200, saved.text
    assert pricing_for_model("openai/unknown-test-model") == (2, 6)
    assert estimate_cost("openai/unknown-test-model", 1000, 500) == pytest.approx(0.005)
    assert (
        c.put(
            "/api/admin/model-providers/models/custom-model", json={**model, "output_cost_per_million": None}
        ).status_code
        == 422
    )
    assert (
        c.put(
            "/api/admin/model-providers/models/custom-model", json={**model, "input_cost_per_million": -1}
        ).status_code
        == 422
    )


@pytest.mark.asyncio
async def test_actual_root_factory_gates_plain_chat_and_records_usage(isolated):
    from google.genai.types import Content, Part

    from adk.agent import create_agent
    from agents.root_runtime import compose_root_skill, root_agent_skill
    from budget.enforcer import BudgetExceededError
    from db.models.root_agent import RootAgentConfig

    # No Skill is loaded: the normal Root agent must enforce its own tenant cap.
    config = RootAgentConfig(model="lite", budgetEnabled=True)
    root = compose_root_skill(root_agent_skill(config), config)
    agent = create_agent(root, A, access_context=build_access_context(A))
    context = SimpleNamespace(invocation_id="root-plain-chat", state={})
    request = SimpleNamespace(
        model="gpt-5.6-luna",
        contents=[Content(role="user", parts=[Part.from_text(text="hello")])],
        config=SimpleNamespace(max_output_tokens=20),
    )
    await agent.before_model_callback(context, request)
    await agent.after_model_callback(
        context,
        SimpleNamespace(partial=False, usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5)),
    )
    assert isolated.query_documents("llm_usage")[0]["tenantId"] == "tenant-a"
    TenantDirectory(isolated).put(TenantConfig(tenantId="tenant-a", quota={"llmBudgetUsd": 0.000000001}))
    with pytest.raises(BudgetExceededError):
        await agent.before_model_callback(context, request)
