"""Effective model registry: YAML bootstrap plus database-backed dynamic models.

The YAML registry remains the GitOps/bootstrap baseline. When the persisted
registry is enabled, enabled dynamic model rows whose provider is also enabled
are overlaid by model id. Persisted registry settings may then override the
platform default and the managed ``default``/``smart``/``fast`` logical tier
aliases. This module intentionally has no cache of database rows so admin
changes are visible immediately to metadata consumers and Agent runtime.
"""

from __future__ import annotations

from pydantic import BaseModel

from config.model_provider_registry import get_provider, list_model_documents, registry_settings
from config.models import ModelEntry, ModelsConfig, load_models_config

MANAGED_TIER_NAMES = ("default", "smart", "fast")


class EffectiveModelEntry(ModelEntry):
    """ModelEntry plus dynamic-provider metadata safe for UI/runtime use."""

    provider_id: str | None = None
    supports_vision: bool = False
    source: str = "yaml"


class EffectiveModelsConfig(BaseModel):
    models: list[EffectiveModelEntry]
    defaults: dict[str, str]
    platform_default: str
    tier_defaults: dict[str, str]
    tier_variants: dict[str, dict[str, str]]
    residency_default_policy: str
    fallback_policy: dict[str, float]


def _yaml_entry(entry: ModelEntry) -> EffectiveModelEntry:
    return EffectiveModelEntry(**entry.model_dump(), source="yaml")


def _dynamic_entry(model_id: str, data: dict) -> EffectiveModelEntry | None:
    if data.get("enabled", True) is False:
        return None
    provider_id = str(data.get("providerId") or "").strip()
    if not provider_id:
        return None
    provider = get_provider(provider_id)
    if provider is None:
        return None
    if str(provider.get("kind") or "openai-compatible") != "openai-compatible":
        return None

    api_name = str(data.get("apiName") or "").strip()
    if not api_name:
        return None

    return EffectiveModelEntry(
        id=model_id,
        api_name=api_name,
        provider="openai",
        provider_id=provider_id,
        tier=str(data.get("tier") or "default"),
        context_window=max(1, int(data.get("contextWindow") or 1)),
        max_output_tokens=max(1, int(data.get("maxOutputTokens") or 1)),
        description=str(data.get("description") or ""),
        supports_tools=data.get("supportsTools", True) is not False,
        supports_reasoning=bool(data.get("supportsReasoning", False)),
        supports_responses_api=bool(data.get("supportsResponsesApi", False)),
        supports_vision=bool(data.get("supportsVision", False)),
        residency=str(data.get("residency") or "global"),
        fallbacks=[],
        source="database",
    )


def _apply_registry_settings(
    base: ModelsConfig,
    by_id: dict[str, EffectiveModelEntry],
) -> tuple[str, dict[str, str], dict[str, dict[str, str]]]:
    """Overlay validated persisted default/tier settings on the YAML baseline.

    Admin writes validate references before persistence. We still treat the
    database as untrusted at read time: a stale reference caused by an out-of-
    band database edit, disabled provider, or removed dynamic model is ignored
    and the corresponding YAML baseline remains active. That keeps registry
    metadata available while runtime residency enforcement continues to be the
    final safety boundary.
    """

    platform_default = base.platform_default
    tier_defaults = dict(base.tier_defaults)
    tier_variants = {name: dict(variants) for name, variants in base.tier_variants.items()}

    settings = registry_settings()
    raw_platform_default = str(settings.get("platformDefault") or "").strip()
    if raw_platform_default in by_id:
        platform_default = raw_platform_default

    raw_tiers = settings.get("tierDefaults")
    if isinstance(raw_tiers, dict):
        for tier in MANAGED_TIER_NAMES:
            target = str(raw_tiers.get(tier) or "").strip()
            if target not in by_id:
                continue
            tier_defaults[tier] = target
            # Persisted mappings are deployment-level aliases. They deliberately
            # replace policy variants for these managed aliases; the Agent
            # residency gate still rejects an illegal target fail-closed.
            tier_variants[tier] = {"default": target}

    return platform_default, tier_defaults, tier_variants


def load_effective_models_config() -> EffectiveModelsConfig:
    """Return YAML baseline overlaid by enabled persisted models and settings."""
    base: ModelsConfig = load_models_config()
    by_id: dict[str, EffectiveModelEntry] = {entry.id: _yaml_entry(entry) for entry in base.models}

    for raw in list_model_documents():
        data = dict(raw)
        model_id = str(data.pop("__id", "")).strip()
        if not model_id:
            continue
        entry = _dynamic_entry(model_id, data)
        if entry is not None:
            by_id[model_id] = entry

    platform_default, tier_defaults, tier_variants = _apply_registry_settings(base, by_id)

    return EffectiveModelsConfig(
        models=sorted(by_id.values(), key=lambda item: item.id.casefold()),
        defaults=dict(base.defaults),
        platform_default=platform_default,
        tier_defaults=tier_defaults,
        tier_variants=tier_variants,
        residency_default_policy=base.residency_default_policy,
        fallback_policy=dict(base.fallback_policy),
    )


def effective_entry_for(ref: str) -> EffectiveModelEntry | None:
    cfg = load_effective_models_config()
    target = cfg.tier_defaults.get(ref, ref)
    return next((entry for entry in cfg.models if entry.id == target), None)


__all__ = [
    "EffectiveModelEntry",
    "EffectiveModelsConfig",
    "MANAGED_TIER_NAMES",
    "effective_entry_for",
    "load_effective_models_config",
]