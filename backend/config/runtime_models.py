from __future__ import annotations

import os
from typing import Literal

from config.effective_models import EffectiveModelEntry, load_effective_models_config
from config.model_provider_registry import get_provider, openai_compatible_runtime, resolve_api_key_ref
from config.models import (
    active_residency_policy,
)
from config.models import (
    api_name_for as yaml_api_name_for,
)
from config.models import (
    provider_for as yaml_provider_for,
)


def entry_for(ref: str) -> EffectiveModelEntry | None:
    cfg = load_effective_models_config()
    variants = cfg.tier_variants.get(ref)
    target = variants.get(active_residency_policy(), variants["default"]) if variants else ref
    return next((entry for entry in cfg.models if entry.id == target), None)


def api_name_for(ref: str) -> str:
    # Metadata resolution stays pure so fallback-chain inspection can determine
    # residency before deciding whether a disallowed fallback should be dropped.
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

    # The policy check above already authorized this ref.  Avoid calling
    # provider_for again merely to discover the legacy credential environment.
    provider = entry.provider if entry is not None else yaml_provider_for(ref)
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
