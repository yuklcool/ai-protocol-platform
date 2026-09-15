"""Pydantic models and effective registry loader for platform models.

``models.yaml`` remains the bootstrap/GitOps source.  In self-host/database
registry mode, persisted ``model_registry`` rows are layered on top so existing
callers (``entry_for``, ``provider_for``, ``GET /api/models`` and Skill Studio)
all see one effective registry rather than a second parallel model system.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

_YAML_PATH = Path(__file__).parent / "models.yaml"


class ChainLink(BaseModel):
    id: str
    location: str | None = None


class ModelEntry(BaseModel):
    id: str
    api_name: str
    provider: Literal["google", "anthropic", "openai"]
    # Dynamic OpenAI-compatible entries point at a persisted provider. YAML
    # entries keep this None and preserve the historical env-based behavior.
    provider_id: str | None = None
    tier: Literal["default", "smart", "fast"]
    context_window: int
    max_output_tokens: int
    description: str
    supports_tools: bool = True
    supports_reasoning: bool = False
    supports_responses_api: bool = False
    supports_vision: bool = False
    residency: Literal["eu", "us", "global"] = "us"
    location: str | None = None
    fallbacks: list[ChainLink] = []


class ModelsConfig(BaseModel):
    models: list[ModelEntry]
    defaults: dict[str, str]
    platform_default: str
    tier_defaults: dict[str, str] = {}
    tier_variants: dict[str, dict[str, str]] = {}
    residency_default_policy: str = "eu-strict"
    fallback_policy: dict[str, float] = {}

    @model_validator(mode="after")
    def validate_references(self) -> "ModelsConfig":
        model_ids = {m.id for m in self.models}
        if self.platform_default not in model_ids:
            raise ValueError(f"platform_default {self.platform_default!r} not found in models list")
        for provider, model_id in self.defaults.items():
            if model_id not in model_ids:
                raise ValueError(f"defaults[{provider!r}] = {model_id!r} not found in models list")
        for tier, variants in self.tier_variants.items():
            for policy, model_id in variants.items():
                if model_id not in model_ids:
                    raise ValueError(f"tier_defaults[{tier!r}][{policy!r}] = {model_id!r} not found in models list")
        for entry in self.models:
            for link in entry.fallbacks:
                if link.id not in model_ids:
                    raise ValueError(f"models[{entry.id!r}].fallbacks references unknown id {link.id!r}")
        return self


def _load_yaml_config() -> ModelsConfig:
    try:
        raw = yaml.safe_load(_YAML_PATH.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"models.yaml not found at {_YAML_PATH}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"models.yaml is malformed: {exc}") from exc

    models: list[ModelEntry] = []
    for key, entry in raw["models"].items():
        fields = {k: v for k, v in entry.items() if k != "id"}
        fields["fallbacks"] = [
            ChainLink(id=link) if isinstance(link, str) else ChainLink(**link)
            for link in fields.get("fallbacks", [])
        ]
        models.append(ModelEntry(id=key, **fields))

    raw_tiers: dict = raw.get("tier_defaults", {})
    tier_variants: dict[str, dict[str, str]] = {}
    for tier, value in raw_tiers.items():
        if isinstance(value, str):
            tier_variants[tier] = {"default": value}
        else:
            if "default" not in value:
                raise RuntimeError(f"models.yaml tier_defaults[{tier!r}] variants need a 'default' key")
            tier_variants[tier] = dict(value)

    return ModelsConfig(
        models=models,
        defaults=raw["defaults"],
        platform_default=raw["platform_default"],
        tier_defaults={tier: variants["default"] for tier, variants in tier_variants.items()},
        tier_variants=tier_variants,
        residency_default_policy=(raw.get("residency") or {}).get("default_policy", "eu-strict"),
        fallback_policy=raw.get("fallback_policy", {}),
    )


def _dynamic_entry(model_id: str, row: dict) -> ModelEntry:
    return ModelEntry(
        id=model_id,
        api_name=str(row.get("apiName") or "").strip(),
        provider="openai",
        provider_id=str(row.get("providerId") or "").strip() or None,
        tier=str(row.get("tier") or "default"),
        context_window=int(row.get("contextWindow") or 1),
        max_output_tokens=int(row.get("maxOutputTokens") or 1),
        description=str(row.get("description") or ""),
        supports_tools=row.get("supportsTools", True) is not False,
        supports_reasoning=bool(row.get("supportsReasoning", False)),
        supports_responses_api=bool(row.get("supportsResponsesApi", False)),
        supports_vision=bool(row.get("supportsVision", False)),
        residency=str(row.get("residency") or "global"),
        fallbacks=[],
    )


def _apply_database_overlay(base: ModelsConfig) -> ModelsConfig:
    from config.model_provider_registry import (
        database_registry_enabled,
        get_provider,
        list_model_documents,
        registry_settings,
    )

    if not database_registry_enabled():
        return base

    effective = {entry.id: entry for entry in base.models}
    for raw in list_model_documents():
        row = dict(raw)
        model_id = str(row.pop("__id", "")).strip()
        if not model_id:
            continue
        # A database row is authoritative for its id. Disabled/misconfigured
        # rows therefore REMOVE an identically named YAML model instead of
        # silently falling back to it.
        if row.get("enabled", True) is False:
            effective.pop(model_id, None)
            continue
        provider_id = str(row.get("providerId") or "").strip()
        if not provider_id or get_provider(provider_id) is None:
            effective.pop(model_id, None)
            continue
        entry = _dynamic_entry(model_id, row)
        if not entry.api_name:
            raise RuntimeError(f"Dynamic model {model_id!r} has no apiName")
        effective[model_id] = entry

    settings = registry_settings()
    platform_default = str(settings.get("platformDefault") or base.platform_default)
    tier_variants = {key: dict(value) for key, value in base.tier_variants.items()}
    raw_tiers = settings.get("tierDefaults")
    if isinstance(raw_tiers, dict):
        for tier, model_id in raw_tiers.items():
            if isinstance(model_id, str) and model_id.strip():
                tier_variants[str(tier)] = {"default": model_id.strip()}

    return ModelsConfig(
        models=list(effective.values()),
        defaults=dict(base.defaults),
        platform_default=platform_default,
        tier_defaults={tier: variants["default"] for tier, variants in tier_variants.items()},
        tier_variants=tier_variants,
        residency_default_policy=base.residency_default_policy,
        fallback_policy=dict(base.fallback_policy),
    )


@lru_cache(maxsize=1)
def load_models_config() -> ModelsConfig:
    """Return the effective YAML + optional database model registry."""
    return _apply_database_overlay(_load_yaml_config())


def clear_models_config_cache() -> None:
    load_models_config.cache_clear()


def _entry_by_id(cfg: ModelsConfig, model_id: str) -> ModelEntry | None:
    return next((m for m in cfg.models if m.id == model_id), None)


RESIDENCY_POLICIES = ("eu-strict", "unrestricted")


def active_residency_policy() -> str:
    import logging
    import os

    value = os.environ.get("MODEL_RESIDENCY_POLICY", "").strip().lower()
    if value in RESIDENCY_POLICIES:
        return value
    if value:
        logging.getLogger(__name__).error(
            "MODEL_RESIDENCY_POLICY=%r is not one of %s — failing safe to 'eu-strict'", value, RESIDENCY_POLICIES
        )
        return "eu-strict"
    default = load_models_config().residency_default_policy
    return default if default in RESIDENCY_POLICIES else "eu-strict"


def _tier_target(cfg: ModelsConfig, name: str) -> str:
    variants = cfg.tier_variants[name]
    return variants.get(active_residency_policy(), variants["default"])


def resolve_tier(name: str) -> ModelEntry:
    cfg = load_models_config()
    if name not in cfg.tier_variants:
        raise ValueError(f"Unknown model tier {name!r}; known tiers: {sorted(cfg.tier_variants)}")
    model_id = _tier_target(cfg, name)
    entry = _entry_by_id(cfg, model_id)
    if entry is None:
        raise ValueError(f"tier {name!r} points at unknown model id {model_id!r}")
    return entry


def entry_for(ref: str) -> ModelEntry | None:
    cfg = load_models_config()
    if ref in cfg.tier_variants:
        ref = _tier_target(cfg, ref)
    return _entry_by_id(cfg, ref)


def api_name_for(ref: str) -> str:
    entry = entry_for(ref)
    return entry.api_name if entry is not None else ref


def provider_for(ref: str) -> Literal["google", "anthropic", "openai"] | None:
    entry = entry_for(ref)
    if entry is not None:
        return entry.provider
    api = api_name_for(ref)
    if api.startswith("gemini-"):
        return "google"
    if api.startswith("claude-"):
        return "anthropic"
    if api.startswith("gpt-") or api.startswith(("o1", "o3", "o4")):
        return "openai"
    return None


def gemini_api_name_for(ref: str) -> str:
    api = api_name_for(ref)
    if not api.startswith("gemini-"):
        raise ValueError(
            f"Expected a Gemini tier here — this call uses Vertex structured output; "
            f"{ref!r} resolved to {api!r}. Use a Gemini tier such as 'lite' or 'pro'."
        )
    return api


def default_model() -> str:
    return resolve_tier_or_default(load_models_config().platform_default)


def resolve_tier_or_default(ref: str) -> str:
    return api_name_for(ref)


def _tier_names() -> set[str]:
    return set(load_models_config().tier_defaults.keys())


# YAML tiers are stable deployment metadata; dynamic model changes do not add
# logical tier *names* at runtime, only retarget them via registry settings.
TIER_NAMES: set[str] = _tier_names()


__all__ = [
    "ChainLink",
    "ModelEntry",
    "ModelsConfig",
    "RESIDENCY_POLICIES",
    "TIER_NAMES",
    "active_residency_policy",
    "api_name_for",
    "clear_models_config_cache",
    "default_model",
    "entry_for",
    "gemini_api_name_for",
    "load_models_config",
    "provider_for",
    "resolve_tier",
    "resolve_tier_or_default",
]
