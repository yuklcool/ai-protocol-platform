"""API tests for platform model default and managed tier mappings."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from config.effective_models import EffectiveModelEntry, EffectiveModelsConfig

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


def _entry(model_id: str, tier: str) -> EffectiveModelEntry:
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


def _cfg(*, mapped: bool = False) -> EffectiveModelsConfig:
    entries = [
        _entry("daily-model", "default"),
        _entry("smart-model", "smart"),
        _entry("fast-model", "fast"),
    ]
    tiers = (
        {"default": "daily-model", "smart": "smart-model", "fast": "fast-model"}
        if mapped
        else {"smart": "smart-model"}
    )
    return EffectiveModelsConfig(
        models=entries,
        defaults={"openai": "daily-model"},
        platform_default="daily-model",
        tier_defaults=tiers,
        tier_variants={name: {"default": target} for name, target in tiers.items()},
        residency_default_policy="unrestricted",
        fallback_policy={},
    )


def test_settings_are_platform_admin_only() -> None:
    client = _client(_TENANT_ADMIN)
    response = client.get("/api/admin/model-registry/settings")
    assert response.status_code == 403


def test_get_settings_exposes_effective_models_and_write_mode() -> None:
    client = _client(_PLATFORM_ADMIN)
    with (
        patch("admin.model_registry_settings_routes.load_effective_models_config", return_value=_cfg()),
        patch("admin.model_registry_settings_routes.registry_settings", return_value={}),
        patch("admin.model_registry_settings_routes.database_registry_enabled", return_value=True),
    ):
        response = client.get("/api/admin/model-registry/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform_default"] == "daily-model"
    assert payload["tier_defaults"] == {"default": "", "smart": "smart-model", "fast": ""}
    assert {row["model_id"] for row in payload["available_models"]} == {
        "daily-model",
        "smart-model",
        "fast-model",
    }
    assert payload["writable"] is True
    assert payload["source"] == "yaml"


def test_put_settings_validates_and_persists_effective_model_references() -> None:
    client = _client(_PLATFORM_ADMIN)
    stored = {
        "platformDefault": "daily-model",
        "tierDefaults": {"default": "daily-model", "smart": "smart-model", "fast": "fast-model"},
    }
    with (
        patch("admin.model_registry_settings_routes.database_registry_enabled", return_value=True),
        patch(
            "admin.model_registry_settings_routes.load_effective_models_config",
            side_effect=[_cfg(), _cfg(mapped=True)],
        ),
        patch("admin.model_registry_settings_routes.registry_settings", return_value=stored),
        patch("admin.model_registry_settings_routes.get_document", return_value=None),
        patch("admin.model_registry_settings_routes.set_document") as write,
        patch("admin.model_registry_settings_routes.record_admin_action") as audit,
    ):
        response = client.put(
            "/api/admin/model-registry/settings",
            json={
                "platform_default": "daily-model",
                "tier_defaults": {
                    "default": "daily-model",
                    "smart": "smart-model",
                    "fast": "fast-model",
                },
            },
        )

    assert response.status_code == 200
    write.assert_called_once_with("model_registry_settings", "default", stored, merge=False)
    assert response.json()["tier_defaults"]["fast"] == "fast-model"
    assert audit.call_args.kwargs["action"] == "update_model_registry_settings"


def test_put_settings_rejects_unknown_or_disabled_model_reference() -> None:
    client = _client(_PLATFORM_ADMIN)
    with (
        patch("admin.model_registry_settings_routes.database_registry_enabled", return_value=True),
        patch("admin.model_registry_settings_routes.load_effective_models_config", return_value=_cfg()),
        patch("admin.model_registry_settings_routes.set_document") as write,
    ):
        response = client.put(
            "/api/admin/model-registry/settings",
            json={
                "platform_default": "daily-model",
                "tier_defaults": {
                    "default": "daily-model",
                    "smart": "missing-model",
                    "fast": "fast-model",
                },
            },
        )

    assert response.status_code == 422
    assert "missing-model" in response.json()["detail"]
    write.assert_not_called()


def test_put_settings_refuses_yaml_only_registry_mode() -> None:
    client = _client(_PLATFORM_ADMIN)
    with patch("admin.model_registry_settings_routes.database_registry_enabled", return_value=False):
        response = client.put(
            "/api/admin/model-registry/settings",
            json={
                "platform_default": "daily-model",
                "tier_defaults": {
                    "default": "daily-model",
                    "smart": "smart-model",
                    "fast": "fast-model",
                },
            },
        )

    assert response.status_code == 409
