"""真实配置存储下的模型接入、探测有效期与平台 Root 应用边界。"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config.platform_config as pc
from auth import User, get_current_user
from config.model_readiness import READINESS_COLLECTION
from config.platform_config import get_platform_config, invalidate_cache, update_platform_config
from db.models import PLATFORM_CONFIG_DOC_ID
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from tests.support.identity import identity_dependency

API = "/api/admin/model-providers"
MODEL = {"api_name": "service-chat", "provider_id": "service", "context_window": 32000, "max_output_tokens": 1024}


@pytest.fixture()
def stack(monkeypatch):
    from admin.model_probe_routes import router as probes
    from admin.model_providers_routes import router as providers
    from admin.platform_config_routes import router as platform_config

    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.setenv("MODEL_REGISTRY_BACKEND", "database")
    monkeypatch.setenv("MODEL_RESIDENCY_POLICY", "unrestricted")
    monkeypatch.setenv("SETUP_KEY", "secret-for-setup")
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    invalidate_cache(clear_last_known_good=True)
    actor = {"user": User(uid="admin", email="admin@example.com", group_tags=frozenset({"aitana-admin"}))}
    app = FastAPI()
    app.include_router(providers, prefix="/api/admin")
    app.include_router(probes, prefix="/api/admin")
    app.include_router(platform_config)
    app.dependency_overrides[get_current_user] = identity_dependency(lambda: actor["user"])
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
    assert current["root_model_id"] == "model"
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
    before = get_platform_config()
    with pytest.raises(ValueError, match="24 小时内"):
        update_platform_config({"agent": {"model": "model"}})
    assert get_platform_config() == before
    assert repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID) is None
    response = client.put("/api/admin/platform-config", json={"agent": {"model": "model"}})
    assert response.status_code == 422
    assert "24 小时内" in response.json()["detail"]
    assert client.post(f"{API}/models/model/use").status_code == 409


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


def test_eu_only_deployment_rejects_non_eu_root_even_after_protocol_tests_pass(stack, monkeypatch):
    client, repo, _ = stack
    probes_pass(client)
    monkeypatch.setenv("MODEL_RESIDENCY_POLICY", "eu-strict")
    assert client.post(f"{API}/models/model/use").status_code == 409
    assert client.get(f"{API}/models/current").json()["residency_policy"] == "eu-strict"
    repo.set_document("model_registry", "model", {"residency": "eu"}, merge=True)
    # Region metadata changes do not alter the wire protocol; the policy guard is evaluated on every application.
    assert client.post(f"{API}/models/model/use").status_code == 200


@pytest.mark.parametrize(
    "state", ["untested", "completion_only", "tool_call_only", "completion_failed", "tool_call_failed"]
)
def test_service_rejects_dynamic_model_without_two_successful_probes(stack, state):
    client, repo, _ = stack
    before = update_platform_config({"agent": {"model": "lite", "instructions": "保留原配置"}})
    stored_before = repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID)
    if state != "untested":
        probes_pass(client)
        raw = repo.get_document(READINESS_COLLECTION, "model")
        if state == "completion_only":
            raw.pop("tool_call")
        elif state == "tool_call_only":
            raw.pop("completion")
        else:
            raw[state.removesuffix("_failed")]["ok"] = False
        repo.set_document(READINESS_COLLECTION, "model", raw)

    with pytest.raises(ValueError, match="24 小时内的普通生成和工具调用测试"):
        update_platform_config({"agent": {"model": "model"}}, updated_by="admin")

    assert get_platform_config() == before
    assert repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID) == stored_before
    response = client.put("/api/admin/platform-config", json={"agent": {"model": "model"}})
    assert response.status_code == 422
    assert client.post(f"{API}/models/model/use").status_code == 409


@pytest.mark.parametrize("via_route", [False, True], ids=["service", "root_save"])
def test_verified_dynamic_model_can_be_saved_through_platform_config(stack, via_route):
    client, repo, _ = stack
    probes_pass(client)
    updates = {"agent": {"model": "model", "instructions": "保留新配置", "tools": ["get_current_time"]}}
    if via_route:
        response = client.put("/api/admin/platform-config", json=updates)
        assert response.status_code == 200, response.text
        config = get_platform_config()
    else:
        config = update_platform_config(updates, updated_by="admin")
    assert config.agent.model == "model"
    assert config.agent.instructions == "保留新配置"
    assert config.agent.tools == ["get_current_time"]
    stored = repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID)
    assert stored["agent"]["model"] == "model"
    assert stored["updatedBy"] == "admin"
    assert stored["updatedAt"] == config.updated_at


@pytest.mark.parametrize(
    "updates",
    [
        {"agent": {"model": "model", "instructions": "更新指令", "tools": ["get_current_time"]}},
        {"preamble": "更新平台提示"},
        {"enabled": False},
        {"compaction": {"tokenThreshold": 3000}},
    ],
    ids=["same_model", "preamble", "enabled", "compaction"],
)
def test_service_saves_other_fields_without_rechecking_active_model(stack, updates):
    client, repo, _ = stack
    probes_pass(client)
    update_platform_config({"agent": {"model": "model"}})
    raw = repo.get_document(READINESS_COLLECTION, "model")
    for result in raw.values():
        result["tested_at"] -= 86401
    repo.set_document(READINESS_COLLECTION, "model", raw)
    assert not client.get(f"{API}/models").json()[0]["readiness"]["ready"]
    invalidate_cache(clear_last_known_good=True)

    with (
        patch("config.platform_config.get_document", wraps=pc.get_document) as read,
        patch("config.platform_config.model_readiness") as readiness,
    ):
        assert get_platform_config().agent.model == "model"
        config = update_platform_config(updates, updated_by="admin")
        assert config.agent.model == "model"
        readiness.assert_not_called()
        assert [call.args for call in read.call_args_list] == [(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID)]

    assert repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID) == config.model_dump(by_alias=True)
    assert client.put("/api/admin/platform-config", json=updates).status_code == 200
    assert client.post(f"{API}/models/model/use").status_code == 409


@pytest.mark.parametrize("model_ref", ["gemini-3-7-flash", "smart", "pro", "default", "fast", "lite"])
def test_service_does_not_require_dynamic_probes_for_file_models_or_aliases(stack, model_ref):
    client, repo, _ = stack
    update_platform_config({"agent": {"model": "another-model"}})
    repo.set_document("model_registry_settings", "default", {"tierDefaults": {"smart": "model"}})
    with patch("config.platform_config.model_readiness") as readiness:
        config = update_platform_config({"agent": {"model": model_ref}})
        assert config.agent.model == model_ref
        readiness.assert_not_called()
    assert client.put("/api/admin/platform-config", json={"agent": {"model": model_ref}}).status_code == 200


@pytest.mark.parametrize("backend", ["file", "yaml", "file_default", "self_hosted_default"])
def test_service_checks_dynamic_models_only_when_database_registry_is_enabled(stack, monkeypatch, backend):
    client, _, _ = stack
    if backend in {"file", "yaml"}:
        monkeypatch.setenv("MODEL_REGISTRY_BACKEND", backend)
    else:
        monkeypatch.delenv("MODEL_REGISTRY_BACKEND")
        if backend == "file_default":
            monkeypatch.setenv("SELF_HOSTED_MODE", "0")
    with (
        patch("config.platform_config.get_document", wraps=pc.get_document) as read,
        patch("config.platform_config.model_readiness", wraps=pc.model_readiness) as readiness,
    ):
        if backend != "self_hosted_default":
            assert update_platform_config({"agent": {"model": "model"}}).agent.model == "model"
            readiness.assert_not_called()
            assert [call.args for call in read.call_args_list] == [(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID)]
        else:
            with pytest.raises(ValueError, match="24 小时内"):
                update_platform_config({"agent": {"model": "model"}})
            readiness.assert_called_once()
    assert client.post(f"{API}/models/model/use").status_code == 409


def test_use_maps_service_readiness_rejection_to_conflict(stack):
    client, repo, _ = stack
    probes_pass(client)

    def invalidate_after_first_check(model_id):
        repo.set_document(READINESS_COLLECTION, model_id, {})
        return {"ready": True}

    with patch("admin.model_probe_routes.model_readiness", side_effect=invalidate_after_first_check):
        response = client.post(f"{API}/models/model/use")
    assert response.status_code == 409
    assert "24 小时内" in response.json()["detail"]
    assert repo.get_document(pc.COLLECTION, PLATFORM_CONFIG_DOC_ID) is None
    assert get_platform_config().agent.model != "model"
