"""真实配置存储下的模型接入、探测有效期与平台 Root 应用边界。"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user
from config.model_readiness import READINESS_COLLECTION
from config.platform_config import get_platform_config, invalidate_cache, update_platform_config
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory

API = "/api/admin/model-providers"
MODEL = {"api_name": "service-chat", "provider_id": "service", "context_window": 32000, "max_output_tokens": 1024}


@pytest.fixture()
def stack(monkeypatch):
    from admin.model_probe_routes import router as probes
    from admin.model_providers_routes import router as providers

    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.setenv("MODEL_REGISTRY_BACKEND", "database")
    monkeypatch.setenv("MODEL_RESIDENCY_POLICY", "unrestricted")
    monkeypatch.setenv("SETUP_KEY", "secret-for-setup")
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    invalidate_cache(clear_last_known_good=True)
    TenantDirectory(repo).put(TenantConfig(tenantId="a"))
    actor = {
        "user": User(uid="admin", email="admin@example.com", tenant_id="a", group_tags=frozenset({"aitana-admin"}))
    }
    app = FastAPI()
    app.include_router(providers, prefix="/api/admin")
    app.include_router(probes, prefix="/api/admin")
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    with TestClient(app) as client:
        assert (
            client.put(
                f"{API}/service",
                json={"name": "模型服务", "base_url": "https://models.example/v1", "api_key_ref": "${SETUP_KEY}"},
            ).status_code
            == 200
        )
        assert client.put(f"{API}/models/model", json=MODEL).status_code == 200
        yield client, repo, actor
    reset_repository_for_testing(None)
    invalidate_cache(clear_last_known_good=True)


def probes_pass(client, *, responses=False):
    async def post(_url, **kwargs):
        payload = kwargs["json"]
        if "tools" in payload:
            function = {"name": "platform_probe", "arguments": '{"value":"OK"}'}
            output = (
                {"output": [{"type": "function_call", **function}]}
                if responses
                else {"choices": [{"message": {"tool_calls": [{"type": "function", "function": function}]}}]}
            )
        else:
            output = (
                {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]}
                if responses
                else {"choices": [{"message": {"content": "OK"}}]}
            )
        return httpx.Response(200, json=output)

    fake = AsyncMock()
    fake.post.side_effect = post
    context = AsyncMock()
    context.__aenter__.return_value = fake
    with patch("admin.model_probe_routes.httpx.AsyncClient", return_value=context):
        for mode in ("completion", "tool_call"):
            response = client.post(f"{API}/models/model/test", json={"mode": mode})
            assert response.status_code == 200 and response.json()["ok"], response.text
    return fake


def test_complete_flow_updates_only_platform_root_and_persists_test_results(stack):
    client, repo, _ = stack
    update_platform_config(
        {"agent": {"model": "lite", "instructions": "keep instructions", "tools": ["get_current_time"]}},
        updated_by="test",
    )
    original = get_platform_config().agent.model_dump()
    assert client.post(f"{API}/models/model/use").status_code == 409
    fake = probes_pass(client)
    for call in fake.post.call_args_list:
        assert call.kwargs["json"].get("max_tokens") == 1024
    result = client.post(f"{API}/models/model/use")
    assert result.status_code == 200, result.text
    assert get_platform_config().agent.model_dump() == {**original, "model": "model"}
    assert repo.get_document("model_registry_settings", "default") is None
    current = client.get(f"{API}/models/current").json()
    assert current["root_model_id"] == current["tenant_model_id"] == "model"
    assert current["root_api_name"] == "service-chat"
    assert client.get(f"{API}/models").json()[0]["readiness"]["ready"]
    assert "secret-for-setup" not in repr(repo.get_document(READINESS_COLLECTION, "model"))
    assert client.delete(f"{API}/models/model").status_code == 409


@pytest.mark.parametrize("change", ["address", "key", "api_name", "tools", "expiry"])
def test_changed_or_expired_configuration_requires_fresh_tests(stack, monkeypatch, change):
    client, repo, _ = stack
    probes_pass(client)
    if change == "address":
        repo.set_document("model_providers", "service", {"baseUrl": "https://different.example/v1"}, merge=True)
    elif change == "key":
        monkeypatch.setenv("SETUP_KEY", "rotated-secret")
    elif change in {"api_name", "tools"}:
        repo.set_document(
            "model_registry",
            "model",
            {"apiName": "different"} if change == "api_name" else {"supportsTools": False},
            merge=True,
        )
    else:
        raw = repo.get_document(READINESS_COLLECTION, "model")
        for value in raw.values():
            value["tested_at"] -= 86401
        repo.set_document(READINESS_COLLECTION, "model", raw)
    assert not client.get(f"{API}/models").json()[0]["readiness"]["ready"]
    assert client.post(f"{API}/models/model/use").status_code == 409


def test_tenant_whitelist_is_reported_without_being_overwritten(stack):
    client, repo, _ = stack
    tenant = TenantDirectory(repo).get("a")
    tenant.model_policy = {"allowedModels": [], "defaultModel": None}
    TenantDirectory(repo).put(tenant)
    probes_pass(client)
    assert client.post(f"{API}/models/model/use").status_code == 200
    assert not client.get(f"{API}/models/current").json()["tenant_allowed"]
    assert TenantDirectory(repo).get("a").model_policy["allowedModels"] == []


def test_responses_models_are_tested_on_responses_endpoint(stack):
    client, repo, _ = stack
    repo.set_document("model_registry", "model", {"supportsResponsesApi": True}, merge=True)
    fake = probes_pass(client, responses=True)
    assert all(call.args[0].endswith("/responses") for call in fake.post.call_args_list)
    assert fake.post.call_args.kwargs["json"]["tool_choice"] == {"type": "function", "name": "platform_probe"}
    assert client.post(f"{API}/models/model/use").status_code == 200


def test_missing_credential_is_not_reported_as_ready_and_tenant_admin_cannot_apply(stack, monkeypatch):
    client, _, actor = stack
    monkeypatch.delenv("SETUP_KEY")
    view = client.get(API).json()[0]
    assert not view["has_api_key"] and view["api_key_ref"] == "${SETUP_KEY}"
    actor["user"] = actor["user"].model_copy(update={"group_tags": frozenset({"tenant-admin:a"})})
    assert client.post(f"{API}/models/model/use").status_code == 403
    assert client.get(f"{API}/models/current").status_code == 403


def test_provider_discovery_returns_names_and_rejects_malformed_lists(stack):
    client, _, _ = stack
    fake = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = fake
    with patch("admin.model_providers_routes.httpx.AsyncClient", return_value=context):
        fake.get.return_value = httpx.Response(200, json={"data": [{"id": "alpha"}, {"id": "beta"}, {"id": "alpha"}]})
        result = client.post(f"{API}/service/test").json()
        assert result["ok"] and result["models"] == ["alpha", "beta"]
        fake.get.return_value = httpx.Response(200, json={"data": "unexpected"})
        assert not client.post(f"{API}/service/test").json()["ok"]


def test_complete_endpoint_url_and_impossible_output_limits_are_rejected(stack):
    client, _, _ = stack
    response = client.put(
        f"{API}/service", json={"name": "bad", "base_url": "https://models.example/v1/chat/completions"}
    )
    assert response.status_code == 422
    assert client.put(f"{API}/models/model", json={**MODEL, "max_output_tokens": 64000}).status_code == 422


def test_tenant_override_is_preserved_and_resolved_separately_from_platform_selection(stack):
    client, repo, _ = stack
    assert client.put(f"{API}/models/tenant-model", json={**MODEL, "api_name": "tenant-chat"}).status_code == 200
    tenant = TenantDirectory(repo).get("a")
    tenant.model_policy = {"allowedModels": ["tenant-model"]}
    TenantDirectory(repo).put(tenant)
    update_platform_config(
        {"agent": {"model": "lite", "tenantOverrides": {"a": {"model": "tenant-model", "instructions": "租户指令"}}}},
        updated_by="test",
    )
    probes_pass(client)
    assert client.post(f"{API}/models/model/use").status_code == 200
    current = client.get(f"{API}/models/current").json()
    assert current["root_model_id"] == "model"
    assert current["tenant_model_id"] == "tenant-model"
    assert current["tenant_allowed"]
    assert get_platform_config().agent.tenant_overrides["a"].instructions == "租户指令"


def test_eu_only_deployment_rejects_non_eu_root_even_after_protocol_tests_pass(stack, monkeypatch):
    client, repo, _ = stack
    probes_pass(client)
    monkeypatch.setenv("MODEL_RESIDENCY_POLICY", "eu-strict")
    assert client.post(f"{API}/models/model/use").status_code == 409
    assert client.get(f"{API}/models/current").json()["residency_policy"] == "eu-strict"
    repo.set_document("model_registry", "model", {"residency": "eu"}, merge=True)
    # Region metadata changes do not alter the wire protocol; the policy guard is evaluated on every application.
    assert client.post(f"{API}/models/model/use").status_code == 200


@pytest.mark.parametrize("reference", ["root_override", "tenant_default", "tenant_whitelist"])
def test_deletion_does_not_orphan_tenant_model_references(stack, reference):
    client, repo, _ = stack
    if reference == "root_override":
        update_platform_config(
            {"agent": {"model": "lite", "tenantOverrides": {"a": {"model": "model"}}}}, updated_by="test"
        )
    else:
        tenant = TenantDirectory(repo).get("a")
        tenant.model_policy = (
            {"defaultModel": "model"} if reference == "tenant_default" else {"allowedModels": ["model"]}
        )
        TenantDirectory(repo).put(tenant)
    assert client.delete(f"{API}/models/model").status_code == 409
    assert repo.get_document("model_registry", "model") is not None
