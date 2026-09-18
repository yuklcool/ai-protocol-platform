from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

_ADMIN = User(uid="admin", email="admin@example.com", domain="example.com", group_tags=frozenset({"aitana-admin"}))
_TENANT = User(uid="tenant", email="ops@example.com", domain="example.com", group_tags=frozenset({"tenant-admin:example.com"}))


def _client(user: User) -> TestClient:
    from admin.model_probe_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api/admin")

    async def current(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = current
    return TestClient(app)


def _docs(collection: str, doc_id: str):
    if collection == "model_registry":
        return {
            "apiName": "deepseek-chat",
            "providerId": "deepseek",
            "supportsTools": True,
            "enabled": True,
        }
    if collection == "model_providers":
        return {
            "baseUrl": "https://api.example/v1",
            "apiKeyRef": "${PROBE_KEY}",
            "enabled": True,
        }
    return None


def _async_client_response(payload: dict, status_code: int = 200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    client = AsyncMock()
    client.post.return_value = response
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = None
    return cm, client


def test_platform_admin_can_run_completion_probe(monkeypatch) -> None:
    monkeypatch.setenv("PROBE_KEY", "secret")
    cm, client = _async_client_response({"choices": [{"message": {"content": "OK"}}]})
    with (
        patch("admin.model_probe_routes.get_document", side_effect=_docs),
        patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm),
    ):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/deepseek-v3/test", json={"mode": "completion"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["content"] == "OK"
    args = client.post.call_args
    assert args.kwargs["json"]["model"] == "deepseek-chat"
    assert args.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_tool_call_probe_requires_requested_function(monkeypatch) -> None:
    monkeypatch.setenv("PROBE_KEY", "secret")
    cm, _ = _async_client_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"type": "function", "function": {"name": "platform_probe", "arguments": '{"value":"ok"}'}}
                        ]
                    }
                }
            ]
        }
    )
    with (
        patch("admin.model_probe_routes.get_document", side_effect=_docs),
        patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm),
    ):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/deepseek-v3/test", json={"mode": "tool_call"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["tool_called"] is True


def test_tool_call_probe_retries_portable_tool_choice_forms(monkeypatch) -> None:
    monkeypatch.setenv("PROBE_KEY", "secret")

    rejected_exact = MagicMock()
    rejected_exact.status_code = 400
    rejected_exact.json.return_value = {"error": {"type": "invalid_request_error"}}

    rejected_required = MagicMock()
    rejected_required.status_code = 422
    rejected_required.json.return_value = {"error": {"type": "invalid_request_error"}}

    accepted_auto = MagicMock()
    accepted_auto.status_code = 200
    accepted_auto.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "platform_probe",
                                "arguments": '{"value":"ok"}',
                            },
                        }
                    ]
                }
            }
        ]
    }

    client = AsyncMock()
    client.post.side_effect = [rejected_exact, rejected_required, accepted_auto]
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = None

    with (
        patch("admin.model_probe_routes.get_document", side_effect=_docs),
        patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm),
    ):
        response = _client(_ADMIN).post(
            "/api/admin/model-providers/models/deepseek-v3/test",
            json={"mode": "tool_call", "prompt": "Call platform_probe now."},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["tool_called"] is True
    assert client.post.await_count == 3

    calls = client.post.call_args_list
    assert calls[0].kwargs["json"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "platform_probe"},
    }
    assert calls[1].kwargs["json"]["tool_choice"] == "required"
    assert calls[2].kwargs["json"]["tool_choice"] == "auto"


def test_tool_call_probe_reports_capability_failure(monkeypatch) -> None:
    monkeypatch.setenv("PROBE_KEY", "secret")
    cm, _ = _async_client_response({"choices": [{"message": {"content": "I cannot call tools"}}]})
    with (
        patch("admin.model_probe_routes.get_document", side_effect=_docs),
        patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm),
    ):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/deepseek-v3/test", json={"mode": "tool_call"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["category"] == "capability"


def test_tenant_admin_cannot_probe_models() -> None:
    response = _client(_TENANT).post("/api/admin/model-providers/models/deepseek-v3/test", json={})
    assert response.status_code == 403


@pytest.mark.parametrize("message", [None, [], "OK", {}, {"content": ""}, {"content": 123}, {"content": []}])
def test_malformed_completion_is_not_success(monkeypatch, message):
    monkeypatch.setenv("PROBE_KEY", "secret")
    cm, _ = _async_client_response({"choices": [{"message": message}]})
    with patch("admin.model_probe_routes.get_document", side_effect=_docs), patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm):
        result = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={}).json()
    assert result["ok"] is False
    assert result["category"] == "schema"


@pytest.mark.parametrize("calls", ["invalid", {}, [None], [{"function": "bad"}], [{"type": "function", "function": {"name": "platform_probe", "arguments": "bad-json"}}], [{"type": "function", "function": {"name": "platform_probe", "arguments": '{"value":123}'}}]])
def test_malformed_tools_are_not_success(monkeypatch, calls):
    monkeypatch.setenv("PROBE_KEY", "secret")
    cm, _ = _async_client_response({"choices": [{"message": {"tool_calls": calls}}]})
    with patch("admin.model_probe_routes.get_document", side_effect=_docs), patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={"mode": "tool_call"})
    assert response.status_code == 200
    assert response.json()["ok"] is False


@pytest.mark.parametrize("status,category", [(401,"authentication"),(403,"authentication"),(429,"protocol"),(500,"protocol"),(302,"protocol")])
def test_http_failures_do_not_echo_upstream_body(monkeypatch, status, category):
    monkeypatch.setenv("PROBE_KEY", "probe-secret")
    cm, _ = _async_client_response({"error": "probe-secret"}, status_code=status)
    with patch("admin.model_probe_routes.get_document", side_effect=_docs), patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={})
    assert response.json()["category"] == category
    assert "probe-secret" not in response.text


def test_transport_errors_do_not_expose_credentials(monkeypatch):
    monkeypatch.setenv("PROBE_KEY", "probe-secret")
    cm, client = _async_client_response({})
    client.post.side_effect = httpx.RemoteProtocolError("upstream echoed probe-secret")
    with patch("admin.model_probe_routes.get_document", side_effect=_docs), patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={})
    assert response.json()["category"] == "network"
    assert "probe-secret" not in response.text


def test_missing_secret_prevents_request(monkeypatch):
    monkeypatch.delenv("PROBE_KEY", raising=False)
    with patch("admin.model_probe_routes.get_document", side_effect=_docs), patch("admin.model_probe_routes.httpx.AsyncClient") as client:
        response = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={})
    assert response.json()["category"] == "configuration"
    client.assert_not_called()


def test_reasoning_probe_omits_unsupported_temperature(monkeypatch):
    monkeypatch.setenv("PROBE_KEY", "probe-secret")
    def documents(collection, doc_id):
        return dict(_docs(collection, doc_id), supportsReasoning=True)
    cm, client = _async_client_response({"choices": [{"message": {"content": "probe-secret OK"}}]})
    with patch("admin.model_probe_routes.get_document", side_effect=documents), patch("admin.model_probe_routes.httpx.AsyncClient", return_value=cm):
        response = _client(_ADMIN).post("/api/admin/model-providers/models/m/test", json={})
    payload = client.post.call_args.kwargs["json"]
    assert "temperature" not in payload and "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 1024
    assert "probe-secret" not in response.text
