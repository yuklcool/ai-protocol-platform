"""API tests for issue #10 model-provider admin control plane."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    uid="tenant-admin",
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


def test_provider_admin_is_platform_only(tenant_admin: TestClient) -> None:
    with patch("admin.model_providers_routes.query_documents", return_value=[]):
        response = tenant_admin.get("/api/admin/model-providers")
    assert response.status_code == 403


def test_put_provider_rejects_plaintext_api_key(platform_admin: TestClient) -> None:
    with patch("admin.model_providers_routes.set_document") as write:
        response = platform_admin.put(
            "/api/admin/model-providers/deepseek",
            json={
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key_ref": "PLAINTEXT_KEY_MUST_BE_REJECTED",
            },
        )
    assert response.status_code == 422
    write.assert_not_called()


def test_put_provider_persists_only_secret_reference_and_redacts_audit(platform_admin: TestClient) -> None:
    with (
        patch("admin.model_providers_routes.get_document", return_value=None),
        patch("admin.model_providers_routes.set_document") as write,
        patch("admin.model_providers_routes.record_admin_action") as audit,
    ):
        response = platform_admin.put(
            "/api/admin/model-providers/deepseek",
            json={
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1/",
                "api_key_ref": "${DEEPSEEK_API_KEY}",
            },
        )

    assert response.status_code == 200
    assert write.call_args.args[2]["apiKeyRef"] == "${DEEPSEEK_API_KEY}"
    assert response.json()["api_key_ref"] == "${DEEPSEEK_API_KEY}"
    audited = audit.call_args.kwargs["after"]
    assert audited["apiKeyRef"] == "<configured>"
    assert "DEEPSEEK_API_KEY" not in repr(audit.call_args)


def test_dynamic_model_requires_existing_provider(platform_admin: TestClient) -> None:
    with (
        patch("admin.model_providers_routes.get_document", return_value=None),
        patch("admin.model_providers_routes.set_document") as write,
    ):
        response = platform_admin.put(
            "/api/admin/model-providers/models/deepseek-v3",
            json={
                "api_name": "deepseek-chat",
                "provider_id": "deepseek",
                "tier": "default",
                "context_window": 128000,
                "max_output_tokens": 8192,
            },
        )
    assert response.status_code == 422
    write.assert_not_called()


def test_dynamic_model_persists_capabilities(platform_admin: TestClient) -> None:
    provider = {"name": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1", "enabled": True}
    with (
        patch("admin.model_providers_routes.get_document", side_effect=[provider, None]),
        patch("admin.model_providers_routes.set_document") as write,
        patch("admin.model_providers_routes.record_admin_action"),
    ):
        response = platform_admin.put(
            "/api/admin/model-providers/models/deepseek-v3",
            json={
                "api_name": "deepseek-chat",
                "provider_id": "deepseek",
                "tier": "default",
                "context_window": 128000,
                "max_output_tokens": 8192,
                "supports_tools": True,
                "supports_reasoning": False,
                "supports_responses_api": False,
                "supports_vision": False,
                "residency": "global",
            },
        )

    assert response.status_code == 200
    written = write.call_args.args[2]
    assert written["providerId"] == "deepseek"
    assert written["supportsTools"] is True
    assert response.json()["model_id"] == "deepseek-v3"


def test_delete_provider_refuses_to_orphan_models(platform_admin: TestClient) -> None:
    provider = {"name": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1"}
    refs = [{"__id": "deepseek-v3", "providerId": "deepseek"}]
    with (
        patch("admin.model_providers_routes.get_document", return_value=provider),
        patch("admin.model_providers_routes.query_documents", return_value=refs),
        patch("admin.model_providers_routes.delete_document") as delete,
    ):
        response = platform_admin.delete("/api/admin/model-providers/deepseek")
    assert response.status_code == 409
    delete.assert_not_called()


def test_provider_test_reports_authentication_failure(platform_admin: TestClient, monkeypatch) -> None:
    provider = {
        "name": "DeepSeek",
        "baseUrl": "https://api.deepseek.com/v1",
        "apiKeyRef": "${DEEPSEEK_API_KEY}",
        "enabled": True,
    }
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_SECRET_VALUE")

    response_mock = MagicMock()
    response_mock.status_code = 401
    client = AsyncMock()
    client.get.return_value = response_mock
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = False

    with (
        patch("admin.model_providers_routes.get_document", return_value=provider),
        patch("admin.model_providers_routes.httpx.AsyncClient", return_value=context),
    ):
        response = platform_admin.post("/api/admin/model-providers/deepseek/test")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["category"] == "authentication"


def test_provider_test_reports_network_failure(platform_admin: TestClient, monkeypatch) -> None:
    provider = {
        "name": "Local",
        "baseUrl": "http://vllm:8000/v1",
        "apiKeyRef": "${VLLM_KEY}",
        "enabled": True,
    }
    monkeypatch.setenv("VLLM_KEY", "TEST_SECRET_VALUE")
    request = httpx.Request("GET", "http://vllm:8000/v1/models")
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("connection refused", request=request)
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = False

    with (
        patch("admin.model_providers_routes.get_document", return_value=provider),
        patch("admin.model_providers_routes.httpx.AsyncClient", return_value=context),
    ):
        response = platform_admin.post("/api/admin/model-providers/local/test")

    assert response.status_code == 200
    assert response.json()["category"] == "network"
