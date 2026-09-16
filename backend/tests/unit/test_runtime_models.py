"""Hermetic tests for runtime dynamic model/provider and tenant-policy resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import runtime_models
from config.effective_models import EffectiveModelEntry, EffectiveModelsConfig
from config.tenant_models import TenantModelAccessError, TenantModelPolicy


@pytest.fixture(autouse=True)
def _unrestricted_tenant_policy():
    # Runtime resolution is task-context aware in production. Keep unrelated
    # unit tests independent from whatever auth context another test installed.
    with patch("config.runtime_models.load_tenant_model_policy", return_value=TenantModelPolicy()):
        yield


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


def _dynamic(model_id: str = "deepseek-v3", api_name: str = "deepseek-chat") -> EffectiveModelEntry:
    return EffectiveModelEntry(
        id=model_id,
        api_name=api_name,
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


def test_tenant_default_overrides_only_logical_default_alias() -> None:
    platform = _dynamic("platform-model", "platform")
    tenant = _dynamic("tenant-model", "tenant")
    cfg = _cfg(platform, tenant).model_copy(
        update={
            "tier_defaults": {"default": platform.id, "smart": platform.id},
            "tier_variants": {
                "default": {"default": platform.id},
                "smart": {"default": platform.id},
            },
        }
    )
    policy = TenantModelPolicy(
        allowedModels=["tenant-model", "platform-model"],
        defaultModel="tenant-model",
    )
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=cfg),
        patch("config.runtime_models.load_tenant_model_policy", return_value=policy),
        patch("config.runtime_models.active_residency_policy", return_value="unrestricted"),
    ):
        assert runtime_models.entry_for("default") is tenant
        assert runtime_models.entry_for("smart") is platform


def test_tenant_whitelist_blocks_primary_before_provider_construction() -> None:
    allowed = _dynamic("allowed-model", "allowed")
    denied = _dynamic("denied-model", "denied")
    policy = TenantModelPolicy(allowedModels=["allowed-model"])
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(allowed, denied)),
        patch("config.runtime_models.load_tenant_model_policy", return_value=policy),
    ):
        assert runtime_models.provider_for("allowed-model") == "openai"
        with pytest.raises(TenantModelAccessError):
            runtime_models.provider_for("denied-model")


def test_tenant_whitelist_marks_denied_fallback_for_existing_chain_filter() -> None:
    allowed = _dynamic("allowed-model", "allowed")
    denied = _dynamic("denied-model", "denied")
    policy = TenantModelPolicy(allowedModels=["allowed-model"])
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(allowed, denied)),
        patch("config.runtime_models.load_tenant_model_policy", return_value=policy),
    ):
        assert runtime_models.provider_key_missing("denied-model") == "tenant-model-policy"


def test_invalid_tenant_default_fails_closed() -> None:
    entry = _dynamic("allowed-model", "allowed")
    policy = TenantModelPolicy(allowedModels=["allowed-model"], defaultModel="missing-model")
    with (
        patch("config.runtime_models.load_effective_models_config", return_value=_cfg(entry)),
        patch("config.runtime_models.load_tenant_model_policy", return_value=policy),
    ):
        with pytest.raises(TenantModelAccessError):
            runtime_models.entry_for("default")


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
