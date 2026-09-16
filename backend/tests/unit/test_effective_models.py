"""Tests for YAML bootstrap + dynamic database model/settings overlay."""

from __future__ import annotations

from unittest.mock import patch

from config.effective_models import effective_entry_for, load_effective_models_config
from config.models import ModelEntry, ModelsConfig


def _base() -> ModelsConfig:
    return ModelsConfig(
        models=[
            ModelEntry(
                id="yaml-model",
                api_name="gpt-yaml",
                provider="openai",
                tier="default",
                context_window=1000,
                max_output_tokens=100,
                description="yaml",
                residency="global",
            )
        ],
        defaults={"openai": "yaml-model"},
        platform_default="yaml-model",
        tier_defaults={"default": "yaml-model"},
        tier_variants={"default": {"default": "yaml-model"}},
        residency_default_policy="unrestricted",
    )


def test_dynamic_model_is_overlaid_and_exposes_provider_metadata() -> None:
    rows = [
        {
            "__id": "deepseek-v3",
            "apiName": "deepseek-chat",
            "providerId": "deepseek",
            "tier": "smart",
            "contextWindow": 128000,
            "maxOutputTokens": 8192,
            "description": "dynamic",
            "supportsTools": True,
            "supportsReasoning": False,
            "supportsResponsesApi": False,
            "supportsVision": False,
            "residency": "global",
            "enabled": True,
        }
    ]
    provider = {
        "kind": "openai-compatible",
        "baseUrl": "https://api.deepseek.com/v1",
        "enabled": True,
    }
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=rows),
        patch("config.effective_models.get_provider", return_value=provider),
        patch("config.effective_models.registry_settings", return_value={}),
    ):
        cfg = load_effective_models_config()

    assert [model.id for model in cfg.models] == ["deepseek-v3", "yaml-model"]
    dynamic = next(model for model in cfg.models if model.id == "deepseek-v3")
    assert dynamic.provider == "openai"
    assert dynamic.provider_id == "deepseek"
    assert dynamic.api_name == "deepseek-chat"
    assert dynamic.source == "database"


def test_dynamic_model_replaces_same_yaml_id() -> None:
    rows = [
        {
            "__id": "yaml-model",
            "apiName": "replacement-model",
            "providerId": "gateway",
            "tier": "default",
            "contextWindow": 2000,
            "maxOutputTokens": 200,
            "enabled": True,
        }
    ]
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=rows),
        patch(
            "config.effective_models.get_provider",
            return_value={"kind": "openai-compatible", "enabled": True},
        ),
        patch("config.effective_models.registry_settings", return_value={}),
    ):
        cfg = load_effective_models_config()

    assert len(cfg.models) == 1
    assert cfg.models[0].api_name == "replacement-model"
    assert cfg.models[0].source == "database"


def test_disabled_or_orphan_dynamic_models_are_not_exposed() -> None:
    rows = [
        {"__id": "disabled", "apiName": "x", "providerId": "p", "enabled": False},
        {"__id": "orphan", "apiName": "y", "providerId": "missing", "enabled": True},
    ]
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=rows),
        patch("config.effective_models.get_provider", return_value=None),
        patch("config.effective_models.registry_settings", return_value={}),
    ):
        cfg = load_effective_models_config()

    assert [model.id for model in cfg.models] == ["yaml-model"]


def test_effective_entry_for_resolves_dynamic_model_id() -> None:
    rows = [
        {
            "__id": "qwen-local",
            "apiName": "qwen3",
            "providerId": "vllm",
            "tier": "fast",
            "contextWindow": 32768,
            "maxOutputTokens": 4096,
            "enabled": True,
        }
    ]
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=rows),
        patch(
            "config.effective_models.get_provider",
            return_value={"kind": "openai-compatible", "enabled": True},
        ),
        patch("config.effective_models.registry_settings", return_value={}),
    ):
        entry = effective_entry_for("qwen-local")

    assert entry is not None
    assert entry.api_name == "qwen3"
    assert entry.provider_id == "vllm"


def test_persisted_platform_default_and_managed_tiers_overlay_yaml_baseline() -> None:
    rows = [
        {
            "__id": "daily-model",
            "apiName": "daily",
            "providerId": "gateway",
            "tier": "default",
            "contextWindow": 128000,
            "maxOutputTokens": 8192,
            "enabled": True,
        },
        {
            "__id": "smart-model",
            "apiName": "smart",
            "providerId": "gateway",
            "tier": "smart",
            "contextWindow": 128000,
            "maxOutputTokens": 8192,
            "enabled": True,
        },
        {
            "__id": "fast-model",
            "apiName": "fast",
            "providerId": "gateway",
            "tier": "fast",
            "contextWindow": 128000,
            "maxOutputTokens": 8192,
            "enabled": True,
        },
    ]
    settings = {
        "platformDefault": "daily-model",
        "tierDefaults": {"default": "daily-model", "smart": "smart-model", "fast": "fast-model"},
    }
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=rows),
        patch(
            "config.effective_models.get_provider",
            return_value={"kind": "openai-compatible", "enabled": True},
        ),
        patch("config.effective_models.registry_settings", return_value=settings),
    ):
        cfg = load_effective_models_config()

    assert cfg.platform_default == "daily-model"
    assert cfg.tier_defaults["default"] == "daily-model"
    assert cfg.tier_defaults["smart"] == "smart-model"
    assert cfg.tier_defaults["fast"] == "fast-model"
    assert cfg.tier_variants["fast"] == {"default": "fast-model"}


def test_stale_persisted_mapping_falls_back_to_yaml_baseline() -> None:
    settings = {
        "platformDefault": "missing-model",
        "tierDefaults": {"default": "missing-model", "smart": "missing-model", "fast": "missing-model"},
    }
    with (
        patch("config.effective_models.load_models_config", return_value=_base()),
        patch("config.effective_models.list_model_documents", return_value=[]),
        patch("config.effective_models.registry_settings", return_value=settings),
    ):
        cfg = load_effective_models_config()

    assert cfg.platform_default == "yaml-model"
    assert cfg.tier_defaults["default"] == "yaml-model"
    assert "smart" not in cfg.tier_defaults
    assert "fast" not in cfg.tier_defaults
