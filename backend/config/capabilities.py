"""Provider-neutral platform capability registry.

The registry is intentionally environment-only: asking what is enabled must not
import Firebase, Vertex, GCS or any other optional cloud SDK.  Startup, health
endpoints and the frontend can therefore inspect capabilities safely on a host
with no GCP credentials.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from config.deployment import is_managed_gcp_mode, is_self_hosted_mode
from config.local_mode import is_local_mode

_FALSE = {"0", "false", "no", "off"}


def _enabled(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE


def _backend(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip().lower() or fallback


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

    def reason_for_cloud(active: bool, label: str) -> str:
        if active:
            return ""
        if self_hosted:
            return f"{label} is optional and disabled in SELF_HOSTED_MODE"
        if local:
            return f"{label} is disabled in LOCAL_MODE"
        return f"{label} is not configured"

    return {
        "auth": Capability(True, auth),
        "persistence": Capability(True, data),
        "session": Capability(True, session),
        "memory": Capability(True, memory),
        "artifacts": Capability(True, artifacts),
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
