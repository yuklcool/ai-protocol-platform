"""Provider-neutral platform capability registry.

The registry is intentionally environment-only: asking what is enabled must not
import Firebase, Vertex, GCS or any other optional cloud SDK. Startup, health
endpoints and the frontend can therefore inspect capabilities safely on a host
with no GCP credentials.

The top-level capability names describe product abilities (LLM, auth, session,
memory, artifacts, remote search, telemetry). Provider-specific entries remain
available as diagnostics, but a disabled optional cloud adapter must never make
the product-level capability look broken.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from config.deployment import is_managed_gcp_mode, is_self_hosted_mode
from config.local_mode import is_local_mode

_FALSE = {"0", "false", "no", "off"}
_TRUE = {"1", "true", "yes", "on"}


def _enabled(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE


def _backend(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip().lower() or fallback


def _llm_capability(*, self_hosted: bool, managed_gcp: bool) -> "Capability":
    """Describe the configured LLM transport without importing a model SDK.

    Self-host prefers an OpenAI-compatible endpoint when ``OPENAI_API_BASE`` is
    present. That covers OpenAI itself as well as DeepSeek/Qwen/vLLM/LiteLLM /
    OneAPI-style gateways because actual model routing remains registry-driven.
    """
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in _TRUE
    if vertex:
        return Capability(True, "vertex")
    if os.environ.get("OPENAI_API_BASE", "").strip():
        return Capability(True, "openai-compatible")
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return Capability(True, "openai")
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return Capability(True, "anthropic")
    if any(os.environ.get(name, "").strip() for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY")):
        return Capability(True, "gemini-api")
    if managed_gcp:
        # Historical managed deployments may obtain Vertex credentials from
        # workload identity/ADC and therefore do not need an API key env var.
        return Capability(True, "vertex")
    reason = "Configure OPENAI_API_BASE + OPENAI_API_KEY or another supported model provider"
    if self_hosted:
        reason += " for SELF_HOSTED_MODE"
    return Capability(False, "none", reason)


@dataclass(frozen=True)
class Capability:
    enabled: bool
    backend: str
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_platform_capabilities() -> dict[str, Capability]:
    """Return the active backend/capability matrix without touching cloud SDKs."""
    local = is_local_mode()
    self_hosted = is_self_hosted_mode()
    managed_gcp = is_managed_gcp_mode()

    auth_default = "stub" if local else ("local-jwt" if self_hosted else "firebase")
    auth = _backend("AUTH_BACKEND", auth_default)

    data_default = "postgres" if self_hosted else ("memory" if local else "firestore")
    data = _backend("DATA_BACKEND", data_default)

    session_default = "postgres" if self_hosted else ("vertex" if os.environ.get("AGENT_ENGINE_ID") else "memory")
    session = _backend("SESSION_BACKEND", session_default)

    memory_default = "postgres" if self_hosted else ("vertex" if os.environ.get("AGENT_ENGINE_ID") else "memory")
    memory = _backend("MEMORY_BACKEND", memory_default)

    artifact_default = "local" if self_hosted else ("gcs" if os.environ.get("ADK_ARTIFACT_BUCKET") else "memory")
    artifacts = _backend("ARTIFACT_BACKEND", artifact_default)

    firebase = auth == "firebase"
    agent_engine = session == "vertex" or memory == "vertex"
    gcs = artifacts == "gcs"
    cloud_trace = managed_gcp and _enabled("TRACE_EXPORT_ENABLED", default=True)
    cloud_logging = managed_gcp and _enabled("CLOUD_LOGGING_ENABLED", default=True)
    vertex_search = managed_gcp and _enabled(
        "VERTEX_SEARCH_ENABLED",
        default=bool(os.environ.get("VERTEX_SEARCH_DATASTORE") or os.environ.get("VERTEX_AI_SEARCH_DATASTORE")),
    )
    llm = _llm_capability(self_hosted=self_hosted, managed_gcp=managed_gcp)

    def reason_for_cloud(active: bool, label: str) -> str:
        if active:
            return ""
        if self_hosted:
            return f"{label} is optional and disabled in SELF_HOSTED_MODE"
        if local:
            return f"{label} is disabled in LOCAL_MODE"
        return f"{label} is not configured"

    # Remote search is a product capability. Vertex Search is only one adapter;
    # when it is off we report the feature as unavailable instead of crashing or
    # pretending the whole platform requires GCP.
    remote_search = Capability(
        vertex_search,
        "vertex" if vertex_search else "none",
        reason_for_cloud(vertex_search, "Remote search"),
    )
    telemetry_enabled = cloud_trace or cloud_logging
    telemetry = Capability(
        telemetry_enabled,
        "gcp" if telemetry_enabled else "disabled",
        reason_for_cloud(telemetry_enabled, "Cloud telemetry"),
    )

    return {
        # Product capabilities used by deployment/UI health surfaces.
        "llm": llm,
        "auth": Capability(True, auth),
        "persistence": Capability(True, data),
        "session": Capability(True, session),
        "memory": Capability(True, memory),
        "artifacts": Capability(True, artifacts),
        "remote_search": remote_search,
        "telemetry": telemetry,
        # Provider diagnostics kept separate from the product-level view.
        "firebase": Capability(firebase, "firebase", reason_for_cloud(firebase, "Firebase")),
        "agent_engine": Capability(agent_engine, "vertex", reason_for_cloud(agent_engine, "Vertex Agent Engine")),
        "gcs": Capability(gcs, "gcs", reason_for_cloud(gcs, "GCS")),
        "vertex_ai_search": Capability(vertex_search, "vertex", reason_for_cloud(vertex_search, "Vertex AI Search")),
        "cloud_trace": Capability(cloud_trace, "gcp", reason_for_cloud(cloud_trace, "Cloud Trace")),
        "cloud_logging": Capability(cloud_logging, "gcp", reason_for_cloud(cloud_logging, "Cloud Logging")),
    }


def capabilities_payload() -> dict[str, object]:
    caps = get_platform_capabilities()
    return {
        "local_mode": is_local_mode(),
        "self_hosted_mode": is_self_hosted_mode(),
        "managed_gcp_mode": is_managed_gcp_mode(),
        "capabilities": {name: capability.to_dict() for name, capability in caps.items()},
    }


__all__ = ["Capability", "capabilities_payload", "get_platform_capabilities"]
