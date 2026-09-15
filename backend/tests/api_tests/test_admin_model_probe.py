from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
