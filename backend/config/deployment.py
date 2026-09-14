"""Deployment-mode helpers shared by startup and capability selection.

``LOCAL_MODE`` is a developer/test mode: it intentionally enables an auth stub
and may use in-memory services.  A production self-host is different: it should
use PostgreSQL, local durable storage and built-in JWT while requiring no GCP
project or Application Default Credentials.

``SELF_HOSTED_MODE=1`` is therefore an explicit deployment boundary, not an
alias for ``LOCAL_MODE``.
"""

from __future__ import annotations

import os

from config.local_mode import is_local_mode

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    raise RuntimeError(f"{name} must be one of 1/0, true/false, yes/no, on/off; got {raw!r}")


def is_self_hosted_mode() -> bool:
    """Return whether this is a production-style self-host deployment."""
    return _env_bool("SELF_HOSTED_MODE", default=False)


def is_managed_gcp_mode() -> bool:
    """Return whether startup may assume the historical managed-GCP runtime.

    Existing cloud deployments remain backwards compatible: if neither
    ``LOCAL_MODE`` nor ``SELF_HOSTED_MODE`` is set, managed GCP remains the
    default.  Self-host never becomes GCP merely because a developer happens to
    have ADC installed on the machine.
    """
    return not is_local_mode() and not is_self_hosted_mode()


def configure_google_genai_environment() -> None:
    """Choose Google GenAI transport without overriding an explicit operator choice.

    In managed-GCP mode the historical default is Vertex AI. In self-host mode
    the default is the Gemini Developer API (API key) so importing the agent
    does not trigger ADC/project discovery. Operators may still explicitly set
    ``GOOGLE_GENAI_USE_VERTEXAI=true`` when they intentionally enable Vertex.
    """
    if is_self_hosted_mode():
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")
    elif is_managed_gcp_mode():
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


def startup_requires_gcp_project() -> bool:
    """Whether the process-wide startup guard must require a GCP project."""
    return is_managed_gcp_mode()


__all__ = [
    "configure_google_genai_environment",
    "is_managed_gcp_mode",
    "is_self_hosted_mode",
    "startup_requires_gcp_project",
]
