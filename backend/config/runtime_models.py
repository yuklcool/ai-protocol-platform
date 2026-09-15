"""Runtime model resolution over the effective YAML + database registry.

This module is the narrow bridge between model metadata and ADK model
construction. It preserves the existing YAML/raw-model compatibility path while
allowing a persisted OpenAI-compatible model to carry its own provider id,
base URL and secret reference without mutating global process environment.
"""

from __future__ import annotations

import os
from typing import Literal

from config.effective_models import EffectiveModelEntry, load_effective_models_config
from config.model_provider_registry import get_provider, openai_compatible_runtime, resolve_api_key_ref
from config.models import (
    active_residency_policy,
    api_name_for as yaml_api_name_for,
    provider_for as yaml_provider_for,
)


def entry_for(ref: str) -> EffectiveModelEntry | None:
    """Resolve tier/id against the effective registry and active residency policy."""
    cfg = load_effective_models_config()
    target = ref
    variants = cfg.tier_variants.get(ref)
    if variants:
        target = variants.get(active_residency_policy(), variants["default"])
    return next((entry for entry in cfg.models if entry.id == target), None)


def api_name_for(ref: str) -> str:
    entry = entry_for(ref)
    return entry.api_name if entry is not None else yaml_api_name_for(ref)


def provider_for(ref: str) -> Literal["google", "anthropic", "openai"] | None:
    entry = entry_for(ref)
    return entry.provider if entry is not None else yaml_provider_for(ref)


def openai_runtime_kwargs(ref: str) -> dict[str, str]:
    """Return request-construction kwargs for one OpenAI-compatible model.

    Persisted dynamic providers use their own ``baseUrl``/``apiKeyRef``.
    YAML/legacy OpenAI entries retain the historical global ``OPENAI_API_BASE``
    behavior and allow LiteLLM to read ``OPENAI_API_KEY`` normally.
    """
    entry = entry_for(ref)
    provider_id = entry.provider_id if entry is not None else None
    if provider_id:
        return openai_compatible_runtime(provider_id)

    kwargs: dict[str, str] = {}
    api_base = os.environ.get("OPENAI_API_BASE", "").strip()
    if api_base:
        kwargs["api_base"] = api_base
    return kwargs


def provider_key_missing(ref: str) -> str | None:
    """Return a missing credential hint for fallback-chain filtering."""
    entry = entry_for(ref)
    if entry is not None and entry.provider_id:
        provider = get_provider(entry.provider_id)
        if provider is None:
            return f"provider:{entry.provider_id}"
        api_key_ref = str(provider.get("apiKeyRef") or "").strip()
        if not api_key_ref:
            return None
        try:
            resolve_api_key_ref(api_key_ref)
        except RuntimeError:
            return api_key_ref
        return None

    provider = provider_for(ref)
    env_name = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider or "")
    if env_name is None:
        return None
    return None if os.environ.get(env_name) else env_name


__all__ = [
    "api_name_for",
    "entry_for",
    "openai_runtime_kwargs",
    "provider_for",
    "provider_key_missing",
]
