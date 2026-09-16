"""Runtime model resolution over the effective YAML + database registry.

This module is the narrow bridge between model metadata and ADK model
construction. It preserves the existing YAML/raw-model compatibility path while
allowing a persisted OpenAI-compatible model to carry its own provider id,
base URL and secret reference without mutating global process environment.

Tenant model authorization is enforced here as the final request-construction
boundary.  The trusted tenant id comes from the auth-bound task context, never
from a model/tool payload.
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
from config.tenant_models import (
    TenantModelAccessError,
    assert_model_allowed,
    load_tenant_model_policy,
)

_TENANT_POLICY_BLOCK = "tenant-model-policy"


def entry_for(ref: str) -> EffectiveModelEntry | None:
    """Resolve tenant default/tier/id against the effective registry.

    ``defaultModel`` is intentionally applied only to the logical ``default``
    alias. Explicit model ids and other tier aliases keep their declared
    meaning and are authorized separately before provider construction.
    """
    cfg = load_effective_models_config()
    target_ref = ref
    policy = load_tenant_model_policy()
    if ref == "default" and policy.default_model:
        target_ref = policy.default_model
        target_entry = next((entry for entry in cfg.models if entry.id == target_ref), None)
        if target_entry is None:
            raise TenantModelAccessError(
                f"Tenant default model {target_ref!r} is unknown or disabled in the effective registry"
            )
        assert_model_allowed(target_entry.id, policy=policy)
        return target_entry

    target = target_ref
    variants = cfg.tier_variants.get(target_ref)
    if variants:
        target = variants.get(active_residency_policy(), variants["default"])
    return next((entry for entry in cfg.models if entry.id == target), None)


def _assert_ref_allowed(ref: str, entry: EffectiveModelEntry | None = None) -> None:
    policy = load_tenant_model_policy()
    if not policy.restricted:
        return
    resolved = entry if entry is not None else entry_for(ref)
    model_id = resolved.id if resolved is not None else ref
    assert_model_allowed(model_id, policy=policy)


def api_name_for(ref: str) -> str:
    # Metadata resolution stays pure so fallback-chain inspection can determine
    # residency before deciding whether a disallowed fallback should be dropped.
    entry = entry_for(ref)
    return entry.api_name if entry is not None else yaml_api_name_for(ref)


def provider_for(ref: str) -> Literal["google", "anthropic", "openai"] | None:
    """Resolve provider and enforce the active tenant allow-list.

    Every primary model construction in ``adk.agent.resolve_model`` crosses
    this function before a provider client is returned, making the whitelist a
    server-side authorization boundary rather than a frontend filter.
    """
    entry = entry_for(ref)
    _assert_ref_allowed(ref, entry)
    return entry.provider if entry is not None else yaml_provider_for(ref)


def openai_runtime_kwargs(ref: str) -> dict[str, str]:
    """Return request-construction kwargs for one OpenAI-compatible model.

    Persisted dynamic providers use their own ``baseUrl``/``apiKeyRef``.
    YAML/legacy OpenAI entries retain the historical global ``OPENAI_API_BASE``
    behavior and allow LiteLLM to read ``OPENAI_API_KEY`` normally.
    """
    entry = entry_for(ref)
    _assert_ref_allowed(ref, entry)
    provider_id = entry.provider_id if entry is not None else None
    if provider_id:
        return openai_compatible_runtime(provider_id)

    kwargs: dict[str, str] = {}
    api_base = os.environ.get("OPENAI_API_BASE", "").strip()
    if api_base:
        kwargs["api_base"] = api_base
    return kwargs


def provider_key_missing(ref: str) -> str | None:
    """Return a missing credential/policy hint for fallback-chain filtering.

    ``adk.agent.resolve_model_chain`` already skips candidates for which this
    helper returns a value. Returning the dedicated tenant-policy sentinel lets
    a disallowed fallback be dropped before any provider request is built,
    while a disallowed primary still fails loudly through ``provider_for``.
    """
    entry = entry_for(ref)
    policy = load_tenant_model_policy()
    if policy.restricted:
        model_id = entry.id if entry is not None else ref
        if not policy.allows(model_id):
            return _TENANT_POLICY_BLOCK

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
