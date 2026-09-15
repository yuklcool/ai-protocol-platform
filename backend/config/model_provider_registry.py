"""Persisted model-provider and dynamic model registry helpers.

YAML remains the bootstrap/GitOps source of truth.  Self-hosted deployments may
layer database-backed providers/models on top by setting
``MODEL_REGISTRY_BACKEND=database`` (the default when SELF_HOSTED_MODE=1).

Secrets are references, never values.  ``apiKeyRef`` must be ``${ENV_VAR}`` and
is resolved only at model construction time.
"""

from __future__ import annotations

import os
import re
from typing import Any

from db.persistence import get_document, query_documents

PROVIDERS_COLLECTION = "model_providers"
MODELS_COLLECTION = "model_registry"
SETTINGS_COLLECTION = "model_registry_settings"
_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def database_registry_enabled() -> bool:
    raw = os.environ.get("MODEL_REGISTRY_BACKEND", "").strip().lower()
    if raw:
        return raw == "database"
    return _truthy(os.environ.get("SELF_HOSTED_MODE"))


def list_provider_documents() -> list[dict[str, Any]]:
    if not database_registry_enabled():
        return []
    return query_documents(PROVIDERS_COLLECTION)


def list_model_documents() -> list[dict[str, Any]]:
    if not database_registry_enabled():
        return []
    return query_documents(MODELS_COLLECTION)


def registry_settings() -> dict[str, Any]:
    if not database_registry_enabled():
        return {}
    return get_document(SETTINGS_COLLECTION, "default") or {}


def get_provider(provider_id: str) -> dict[str, Any] | None:
    if not database_registry_enabled():
        return None
    doc = get_document(PROVIDERS_COLLECTION, provider_id)
    if not doc or doc.get("enabled", True) is False:
        return None
    return doc


def resolve_api_key_ref(api_key_ref: str | None) -> str | None:
    ref = (api_key_ref or "").strip()
    if not ref:
        return None
    match = _ENV_REF.fullmatch(ref)
    if match is None:
        raise RuntimeError("Provider apiKeyRef must use ${ENV_VAR}; plaintext API keys are not supported")
    env_name = match.group(1)
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise RuntimeError(f"Provider secret reference ${{{env_name}}} is unset or empty")
    return value


def openai_compatible_runtime(provider_id: str | None) -> dict[str, str]:
    """Return LiteLLM kwargs for a persisted OpenAI-compatible provider.

    Empty dict means the model should use the historical global OPENAI env
    configuration.  A configured provider fails loudly when its secret ref is
    unresolved rather than silently falling back to another credential.
    """
    if not provider_id:
        return {}
    provider = get_provider(provider_id)
    if provider is None:
        raise RuntimeError(f"Model provider {provider_id!r} is missing or disabled")
    kind = str(provider.get("kind") or "openai-compatible")
    if kind != "openai-compatible":
        raise RuntimeError(f"Unsupported dynamic provider kind {kind!r}")

    result: dict[str, str] = {}
    base_url = str(provider.get("baseUrl") or "").strip()
    if base_url:
        result["api_base"] = base_url.rstrip("/")
    api_key = resolve_api_key_ref(provider.get("apiKeyRef"))
    if api_key:
        result["api_key"] = api_key
    return result


def provider_view(provider_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Redacted provider representation safe for Admin/API responses."""
    return {
        "provider_id": provider_id,
        "name": str(data.get("name") or provider_id),
        "kind": str(data.get("kind") or "openai-compatible"),
        "base_url": str(data.get("baseUrl") or ""),
        "enabled": data.get("enabled", True) is not False,
        "api_key_ref": str(data.get("apiKeyRef") or "") or None,
        "has_api_key": bool(data.get("apiKeyRef")),
    }


__all__ = [
    "MODELS_COLLECTION",
    "PROVIDERS_COLLECTION",
    "SETTINGS_COLLECTION",
    "database_registry_enabled",
    "get_provider",
    "list_model_documents",
    "list_provider_documents",
    "openai_compatible_runtime",
    "provider_view",
    "registry_settings",
    "resolve_api_key_ref",
]
