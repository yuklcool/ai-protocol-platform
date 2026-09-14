"""GCP project and credential resolution.

GCP is a provider, not a process-wide prerequisite. Managed deployments keep
the historical env/ADC fallback. ``SELF_HOSTED_MODE=1`` does not probe ADC or
require a project unless an operator explicitly selects a GCP-backed capability.
"""

from __future__ import annotations

import logging
import os

import google.auth
import google.auth.credentials
import google.auth.exceptions

from config.deployment import is_self_hosted_mode

_log = logging.getLogger(__name__)

# API-key env vars that, in Vertex mode, poison the genai client.
_API_KEY_VARS = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def selfhost_gcp_capability_requested() -> bool:
    """Return True only when a self-host explicitly opted into a GCP provider.

    Merely having ``google-auth`` installed, or stale ADC on the machine, must
    never turn a PostgreSQL/local/JWT deployment into a GCP deployment.
    """
    if not is_self_hosted_mode():
        return True
    return any(
        (
            os.environ.get("AUTH_BACKEND", "").strip().lower() == "firebase",
            os.environ.get("SESSION_BACKEND", "").strip().lower() == "vertex",
            os.environ.get("MEMORY_BACKEND", "").strip().lower() == "vertex",
            os.environ.get("ARTIFACT_BACKEND", "").strip().lower() == "gcs",
            os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() == "true",
            _truthy("VERTEX_SEARCH_ENABLED"),
            _truthy("TRACE_EXPORT_ENABLED"),
            _truthy("CLOUD_LOGGING_ENABLED"),
            bool(os.environ.get("AGENT_ENGINE_ID")),
            bool(os.environ.get("ADK_ARTIFACT_BUCKET")),
        )
    )


def neutralize_api_key_in_vertex_mode() -> list[str]:
    """Self-heal a deploy that sets an API key alongside Vertex mode.

    When ``GOOGLE_GENAI_USE_VERTEXAI=true``, the google-genai client attaches any
    ``GOOGLE_API_KEY`` / ``GEMINI_API_KEY`` / ``GOOGLE_GENAI_API_KEY`` in the env
    to Vertex calls, and Vertex Sessions/Memory reject API-key auth with a 401
    ``CREDENTIALS_MISSING`` — which silently breaks *every* chat turn. A deploy
    that mounts one of these (e.g. via a shared secret-env list) would otherwise
    take the whole service down.

    Pop the offending vars — but only in Vertex mode — so the app is robust to
    the misconfiguration regardless of what the deploy injects. MUST be called
    before any genai client is created (i.e. at import of the app entrypoint).
    Logs loudly so the deploy env still gets cleaned up at the source. Returns
    the names it popped (for tests / callers that want to log a summary).
    """
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "true":
        return []
    leaked = [v for v in _API_KEY_VARS if os.getenv(v)]
    for v in leaked:
        os.environ.pop(v, None)
    if leaked:
        _log.error(
            "STARTUP: unset %s because GOOGLE_GENAI_USE_VERTEXAI=true — an API key "
            "in env makes Vertex Sessions/Memory reject auth with 401 "
            "CREDENTIALS_MISSING and breaks every chat turn. Auto-corrected so the "
            "service works; REMOVE these from the deployed env — they must not be "
            "set in Vertex mode.",
            ", ".join(leaked),
        )
    return leaked


def resolve_gcp_credentials() -> tuple[google.auth.credentials.Credentials, str | None] | None:
    """Return ``(credentials, adc_project)`` or ``None`` when ADC is unavailable.

    In the default self-host profile this returns ``None`` *without calling*
    ``google.auth.default()``. That matters because ADC discovery may consult
    local gcloud files or metadata endpoints even when the operator never
    enabled a GCP capability.
    """
    if is_self_hosted_mode() and not selfhost_gcp_capability_requested():
        return None
    try:
        creds, adc_project = google.auth.default()
        return creds, adc_project
    except google.auth.exceptions.DefaultCredentialsError:
        return None


def resolve_gcp_project() -> str | None:
    """Return the resolved GCP project ID, or None if unavailable."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if project:
        return project
    resolved = resolve_gcp_credentials()
    return resolved[1] if resolved else None


def require_gcp_project() -> str:
    """Same as :func:`resolve_gcp_project` but raises when unavailable."""
    project = resolve_gcp_project()
    if not project:
        raise RuntimeError(
            "No GCP project available for the selected GCP capability: set "
            "GOOGLE_CLOUD_PROJECT/GCP_PROJECT and credentials, or switch that "
            "capability to a self-host backend."
        )
    return project


#: Sentinel used by legacy managed-GCP imports when no project resolves. Kept
#: for backwards compatibility; SELF_HOSTED_MODE never installs it.
PLACEHOLDER_PROJECT = "unset-project"


class ProjectGuardError(RuntimeError):
    """Raised when the resolved GCP project is provably wrong for this deployment."""


def check_startup_project(*, local_mode: bool) -> str:
    """Validate the managed-GCP project at boot. Returns a descriptive value.

    LOCAL_MODE and SELF_HOSTED_MODE are process-wide exemptions because neither
    mode requires GCP. Individual optional GCP backends call
    :func:`require_gcp_project` when they are constructed, so selecting Vertex
    or GCS in a self-host still fails loudly at the provider boundary rather
    than weakening validation.
    """
    resolved = resolve_gcp_project()

    if local_mode:
        return resolved or "(local-mode)"
    if is_self_hosted_mode():
        return resolved or "(self-hosted)"

    if not resolved:
        raise ProjectGuardError(
            "No GCP project resolved at startup. Set GOOGLE_CLOUD_PROJECT "
            "(or GCP_PROJECT), configure ADC, or use SELF_HOSTED_MODE=1 for a "
            "PostgreSQL/local-storage deployment that does not require GCP."
        )

    if resolved == PLACEHOLDER_PROJECT:
        raise ProjectGuardError(
            f"GCP project is the placeholder {PLACEHOLDER_PROJECT!r}, which means none was "
            "configured. Set GOOGLE_CLOUD_PROJECT (or PLATFORM_DEFAULT_PROJECT) to the real "
            "project, or use SELF_HOSTED_MODE=1 to run without GCP."
        )

    expected = os.getenv("PLATFORM_EXPECTED_PROJECT", "").strip()
    if expected and resolved != expected:
        raise ProjectGuardError(
            f"GCP project mismatch: resolved {resolved!r} but PLATFORM_EXPECTED_PROJECT "
            f"is {expected!r}. Refusing to start rather than read/write the wrong "
            f"project. Fix GOOGLE_CLOUD_PROJECT / GCP_PROJECT, or update "
            f"PLATFORM_EXPECTED_PROJECT if this deployment really did move."
        )

    return resolved


__all__ = [
    "PLACEHOLDER_PROJECT",
    "ProjectGuardError",
    "check_startup_project",
    "neutralize_api_key_in_vertex_mode",
    "require_gcp_project",
    "resolve_gcp_credentials",
    "resolve_gcp_project",
    "selfhost_gcp_capability_requested",
]
