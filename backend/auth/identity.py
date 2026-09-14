"""Authentication backend selection for self-host and cloud deployments.

Business code continues to depend on ``auth.get_current_user`` and the shared
``User`` model. This module only decides which identity provider is active;
providers must all return the same trusted ``User`` shape.
"""

from __future__ import annotations

import os
from typing import Literal, Protocol, runtime_checkable

from fastapi import Request

from auth.models import User
from config.local_mode import is_local_mode

AuthBackend = Literal["stub", "firebase", "local-jwt", "oidc"]


@runtime_checkable
class IdentityProvider(Protocol):
    async def get_current_user(self, request: Request) -> User: ...


def auth_backend() -> AuthBackend:
    """Return the configured auth backend.

    Explicit ``AUTH_BACKEND`` always wins. For backwards compatibility, an
    unset value keeps the historical behavior: LOCAL_MODE uses the stub and
    cloud mode uses Firebase. The insecure stub is never accepted outside
    LOCAL_MODE.
    """
    raw = os.environ.get("AUTH_BACKEND", "").strip().lower()
    if not raw:
        return "stub" if is_local_mode() else "firebase"
    aliases = {
        "local": "local-jwt",
        "jwt": "local-jwt",
        "local_jwt": "local-jwt",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"stub", "firebase", "local-jwt", "oidc"}:
        raise RuntimeError(
            f"Unsupported AUTH_BACKEND={raw!r}; expected stub, firebase, local-jwt, or oidc"
        )
    if raw == "stub" and not is_local_mode():
        raise RuntimeError("AUTH_BACKEND=stub is only allowed when LOCAL_MODE=1")
    return raw  # type: ignore[return-value]


__all__ = ["AuthBackend", "IdentityProvider", "auth_backend"]
