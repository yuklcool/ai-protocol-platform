"""Hermetic tests for runtime dynamic model/provider resolution."""

from __future__ import annotations

from unittest.mock import patch

from config.effective_models import EffectiveModelEntry, EffectiveModelsConfig
from config import runtime_models


def _cfg(*entries: EffectiveModelEntry) -> EffectiveModelsConfig:
    return EffectiveModelsConfig(
        models=list(entries),
        defaults={"openai": entries[0].id if entries else "x"},
        platform_default=entries[0].id if entries else "x",
        tier_defaults={"smart": entries[0].id if entries else "x"},
        tier_variants={"smart": {"default": entries[0].id if entries else "x"}},
        residency_default_policy="unrestricted",
        fallback_policy={},
    )


def _dynamic() -> EffectiveModelEntry:
    return EffectiveModelEntry(
        id="deepseek-v3",
        api_name="deepseek-chat",
        provider="openai",
        provider_id="deepseek",
        tier="smart",
        context_window=128000,
        max_output_tokens=8192,
        description="dynamic",
        supports_tools=True,
        residency="global",
        source="database",
    )


def test_dynamic_entry_and_provider_are_resolved() -> None:
    entry = _dynamic()
    with patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)):
        resolved = runtime_models.entry_for("deepseek-v3")
        assert resolved is entry
        assert runtime_models.api_name_for("deepseek-v3") == "deepseek-chat"
        assert runtime_models.provider_for("deepseek-v3") == "openai"


def test_tier_resolves_against_effective_registry() -> None:
    entry = _dynamic()
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)),
        patch("config.runtime_models.active_residency_policy", return_value="unrestricted"),
    ):
        assert runtime_models.entry_for("smart") is entry


def test_managed_default_and_fast_tiers_reach_runtime_resolver() -> None:
    entry = _dynamic()
    cfg = _cfg(entry).model_copy(
        update={
            "tier_defaults": {"default": entry.id, "smart": entry.id, "fast": entry.id},
            "tier_variants": {
                "default": {"default": entry.id},
                "smart": {"default": entry.id},
                "fast": {"default": entry.id},
            },
        }
    )
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=cfg),
        patch("config.runtime_models.active_residency_policy", return_value="unrestricted"),
    ):
        assert runtime_models.entry_for("default") is entry
        assert runtime_models.entry_for("fast") is entry
        assert runtime_models.api_name_for("default") == "deepseek-chat"


def test_dynamic_openai_provider_uses_provider_specific_runtime_kwargs() -> None:
    entry = _dynamic()
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)),
        patch(
            "config.runtime_models.openai_compatible_runtime",
            return_value={"api_base": "https://api.deepseek.com/v1", "api_key": "secret"},
        ) as runtime,
    ):
        kwargs = runtime_models.openai_runtime_kwargs("deepseek-v3")

    assert kwargs == {"api_base": "https://api.deepseek.com/v1", "api_key": "secret"}
    runtime.assert_called_once_with("deepseek")


def test_yaml_openai_model_preserves_global_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "https://gateway.example/v1")
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg()),
        patch("config.runtime_models.yaml_api_name_for", return_value="gpt-5"),
    ):
        assert runtime_models.openai_runtime_kwargs("gpt-5") == {
            "api_base": "https://gateway.example/v1"
        }


def test_dynamic_provider_missing_secret_is_reported_without_global_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entry = _dynamic()
    provider = {"apiKeyRef": "${DEEPSEEK_API_KEY}", "enabled": True}
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)),
        patch("config.runtime_models.get_provider", return_value=provider),
        patch("config.runtime_models.resolve_api_key_ref", side_effect=RuntimeError("missing")),
    ):
        assert runtime_models.provider_key_missing("deepseek-v3") == "${DEEPSEEK_API_KEY}"


def test_dynamic_provider_with_resolved_secret_does_not_require_global_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entry = _dynamic()
    provider = {"apiKeyRef": "${DEEPSEEK_API_KEY}", "enabled": True}
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)),
        patch("config.runtime_models.get_provider", return_value=provider),
        patch("config.runtime_models.resolve_api_key_ref", return_value="secret"),
    ):
        assert runtime_models.provider_key_missing("deepseek-v3") is None
