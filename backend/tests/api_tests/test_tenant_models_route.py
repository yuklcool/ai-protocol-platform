"""Tenant-aware GET /api/models filtering while preserving anonymous metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User
from config.effective_models import EffectiveModelEntry, EffectiveModelsConfig
from config.tenant_models import TenantModelPolicy
from protocols.models_route import router


def _entry(model_id: str, tier: str = "default") -> EffectiveModelEntry:
    return EffectiveModelEntry(
        id=model_id,
        api_name=model_id,
        provider="openai",
        tier=tier,
        context_window=128000,
        max_output_tokens=8192,
        description=model_id,
        residency="global",
        source="yaml",
    )


def _cfg() -> EffectiveModelsConfig:
    a = _entry("model-a")
    b = _entry("model-b", "smart")
    return EffectiveModelsConfig(
        models=[a, b],
        defaults={"openai": "model-a"},
        platform_default="model-a",
        tier_defaults={"default": "model-a", "smart": "model-b"},
        tier_variants={
            "default": {"default": "model-a"},
            "smart": {"default": "model-b"},
        },
        residency_default_policy="unrestricted",
        fallback_policy={},
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_anonymous_metadata_remains_unfiltered() -> None:
    with patch("protocols.models_route.load_effective_models_config", return_value=_cfg()):
        response = _client().get("/api/models")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["models"]} == {"model-a", "model-b"}
    assert response.json()["platform_default"] == "model-a"


def test_authenticated_tenant_only_sees_allowlisted_models() -> None:
    user = User(
        uid="user-a",
        email="user@a.example",
        domain="a.example",
        tenant_id="tenant-a",
    )
    policy = TenantModelPolicy(allowedModels=["model-b"], defaultModel="model-b")
    with (
        patch("protocols.models_route.load_effective_models_config", return_value=_cfg()),
        patch("protocols.models_route.get_current_user", new=AsyncMock(return_value=user)) as auth,
        patch("protocols.models_route.load_tenant_model_policy", return_value=policy) as load_policy,
    ):
        response = _client().get("/api/models", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["models"]] == ["model-b"]
    assert body["platform_default"] == "model-b"
    assert body["tier_defaults"] == {"smart": "model-b", "default": "model-b"}
    assert body["defaults"] == {}
    auth.assert_awaited_once()
    load_policy.assert_called_once_with("tenant-a")


def test_explicit_empty_whitelist_returns_no_tenant_models() -> None:
    user = User(uid="user-a", tenant_id="tenant-a")
    policy = TenantModelPolicy(allowedModels=[])
    with (
        patch("protocols.models_route.load_effective_models_config", return_value=_cfg()),
        patch("protocols.models_route.get_current_user", new=AsyncMock(return_value=user)),
        patch("protocols.models_route.load_tenant_model_policy", return_value=policy),
    ):
        response = _client().get("/api/models", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["models"] == []
    assert response.json()["defaults"] == {}
    assert response.json()["tier_defaults"] == {}
    assert response.json()["platform_default"] == ""
