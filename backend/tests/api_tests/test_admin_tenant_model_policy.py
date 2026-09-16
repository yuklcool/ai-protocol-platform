"""API coverage for first-class tenant model whitelist/default management."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from config.effective_models import EffectiveModelEntry, EffectiveModelsConfig
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory

_PLATFORM_ADMIN = User(
    uid="platform-admin",
    email="owner@example.net",
    domain="example.net",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT_ADMIN = User(
    uid="tenant-admin",
    email="ops@a.example",
    domain="a.example",
    tenant_id="tenant-a",
    group_tags=frozenset({"tenant-admin:tenant-a"}),
)


@pytest.fixture(autouse=True)
def _repo():
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    TenantDirectory(repo).put(
        TenantConfig(
            tenantId="tenant-a",
            displayName="Tenant A",
            domains=["a.example"],
        )
    )
    yield repo
    reset_repository_for_testing(None)


def _client(user: User) -> TestClient:
    from admin.routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


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
    entries = [_entry("model-a"), _entry("model-b", "smart")]
    return EffectiveModelsConfig(
        models=entries,
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


def test_platform_admin_can_set_whitelist_and_default(_repo) -> None:
    client = _client(_PLATFORM_ADMIN)
    with (
        patch("admin.tenant_model_policy_routes.load_effective_models_config", return_value=_cfg()),
        patch("admin.tenant_model_policy_routes.record_admin_action") as audit,
    ):
        response = client.put(
            "/api/admin/tenant-model-policies/tenant-a",
            json={"allowed_models": ["model-b"], "default_model": "model-b"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["allowed_models"] == ["model-b"]
    assert body["default_model"] == "model-b"
    assert body["effective_default_model"] == "model-b"
    assert {item["model_id"]: item["allowed"] for item in body["available_models"]} == {
        "model-a": False,
        "model-b": True,
    }
    stored = _repo.get_document("tenants", "tenant-a")
    assert stored["modelPolicy"] == {"allowedModels": ["model-b"], "defaultModel": "model-b"}
    assert audit.call_args.kwargs["action"] == "update_tenant_model_policy"


def test_tenant_admin_cannot_expand_its_own_model_policy() -> None:
    client = _client(_TENANT_ADMIN)
    response = client.put(
        "/api/admin/tenant-model-policies/tenant-a",
        json={"allowed_models": None, "default_model": None},
    )
    assert response.status_code == 403


def test_unknown_model_is_rejected_before_write(_repo) -> None:
    before = _repo.get_document("tenants", "tenant-a")
    with patch("admin.tenant_model_policy_routes.load_effective_models_config", return_value=_cfg()):
        response = _client(_PLATFORM_ADMIN).put(
            "/api/admin/tenant-model-policies/tenant-a",
            json={"allowed_models": ["missing"], "default_model": None},
        )
    assert response.status_code == 422
    assert "missing" in response.text
    assert _repo.get_document("tenants", "tenant-a") == before


def test_default_must_be_inside_explicit_whitelist() -> None:
    with patch("admin.tenant_model_policy_routes.load_effective_models_config", return_value=_cfg()):
        response = _client(_PLATFORM_ADMIN).put(
            "/api/admin/tenant-model-policies/tenant-a",
            json={"allowed_models": ["model-a"], "default_model": "model-b"},
        )
    assert response.status_code == 422
    assert "defaultModel" in response.text


def test_explicit_empty_whitelist_is_persisted_as_deny_all(_repo) -> None:
    with (
        patch("admin.tenant_model_policy_routes.load_effective_models_config", return_value=_cfg()),
        patch("admin.tenant_model_policy_routes.record_admin_action"),
    ):
        response = _client(_PLATFORM_ADMIN).put(
            "/api/admin/tenant-model-policies/tenant-a",
            json={"allowed_models": [], "default_model": None},
        )
    assert response.status_code == 200, response.text
    assert response.json()["allowed_models"] == []
    assert response.json()["effective_default_model"] is None
    assert _repo.get_document("tenants", "tenant-a")["modelPolicy"] == {"allowedModels": []}


def test_legacy_domain_bridge_is_not_silently_migrated(_repo) -> None:
    _repo.set_document("clients", "legacy.example", {"display_name": "Legacy"})
    response = _client(_PLATFORM_ADMIN).get(
        "/api/admin/tenant-model-policies/legacy.example"
    )
    assert response.status_code == 409
    assert _repo.get_document("tenants", "legacy.example") is None
