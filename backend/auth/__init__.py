"""Unified authentication entry point.

All business routes should continue importing ``get_current_user`` from this
module. The active verifier is selected by ``AUTH_BACKEND`` and every provider
returns the same trusted ``User`` / ``AccessContext`` shape.

Provider SDKs are imported lazily so Self-host/local-JWT startup does not pull
Firebase Admin into the core identity path.
"""

import logging
import os

import jwt
from fastapi import HTTPException, Request

from auth.access_context import AccessContext, build_access_context, can_access
from auth.group_id_auth import AUTH_MODE as _GROUP_AUTH_MODE
from auth.group_id_auth import AnonymousGroupAuth, GroupRevoked, InvalidGroupToken
from auth.identity import auth_backend
from auth.models import User
from auth.permissions import ToolPermissionDenied, can_use_tool
from config.local_mode import is_local_mode

logger = logging.getLogger(__name__)


def _peek_token_auth_mode(token: str) -> str | None:
    """Read an unverified auth_mode claim only to route to a real verifier."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return None
    mode = unverified.get("auth_mode")
    return mode if isinstance(mode, str) else None


async def _group_auth_get_current_user(request: Request, token: str) -> User:
    try:
        user = AnonymousGroupAuth.user_from_token(token)
    except GroupRevoked as exc:
        logger.info("auth: rejected revoked group token")
        raise HTTPException(status_code=401, detail="group revoked") from exc
    except InvalidGroupToken as exc:
        logger.info("auth: rejected invalid group token (%s)", exc)
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    request.state.access = build_access_context(user)
    logger.info("auth: group-auth uid=%s group=%s", user.uid, user.group_id)
    return user


_ALLOWLIST_TRUTHY = {"1", "true", "yes", "on"}


def _require_known_domain() -> bool:
    return os.environ.get("AUTH_REQUIRE_KNOWN_DOMAIN", "").strip().lower() in _ALLOWLIST_TRUTHY


def _operator_domains() -> frozenset[str]:
    raw = os.environ.get("AUTH_OPERATOR_DOMAINS", "")
    return frozenset(d.strip().lower() for d in raw.split(",") if d.strip())


def _domain_allowed(user: User) -> bool:
    domain = (user.domain or "").strip().lower()
    if not domain:
        return False
    if domain in _operator_domains():
        return True
    from db.clients import get_client_cached

    return get_client_cached(domain) is not None


def _enforce_domain_allowlist(user: User) -> None:
    if not _require_known_domain():
        return
    if is_local_mode():
        return
    if user.auth_mode == _GROUP_AUTH_MODE:
        return
    if _domain_allowed(user):
        return
    if not _operator_domains():
        logger.error(
            "AUTH_OPERATOR_DOMAINS_MISSING: AUTH_REQUIRE_KNOWN_DOMAIN is on but "
            "AUTH_OPERATOR_DOMAINS is empty — only mapped tenants can authenticate. "
            "Set it in this env's deployment configuration (uid=%s domain=%s)",
            user.uid,
            user.domain or "(none)",
        )
    logger.info("auth: rejected domain uid=%s domain=%s", user.uid, user.domain or "(none)")
    raise HTTPException(
        status_code=403,
        detail={
            "code": "DOMAIN_NOT_PERMITTED",
            "message": "This account's domain isn't permitted on this deployment.",
        },
    )


async def get_current_user(request: Request) -> User:
    """Authenticate once, enforce deployment policy, and bind tenant tracing."""
    from observability.tenant_context import set_tenant_context

    user = await _resolve_user(request)
    _enforce_domain_allowlist(user)
    set_tenant_context(user)
    return user


async def _resolve_user(request: Request) -> User:
    """Dispatch to the configured provider without changing route call sites."""
    backend = auth_backend()

    if backend == "local-jwt":
        from auth.local_jwt import get_current_user_local_jwt

        return await get_current_user_local_jwt(request)

    if backend == "oidc":
        from auth.oidc import get_current_user_oidc

        return await get_current_user_oidc(request)

    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()

    if token and _peek_token_auth_mode(token) == _GROUP_AUTH_MODE:
        return await _group_auth_get_current_user(request, token)

    if backend == "stub":
        from auth.local_mode_stub import get_current_user_local_mode

        return await get_current_user_local_mode(request)

    # Provider-specific SDK stays outside the Self-host startup path.
    from auth.firebase_auth import get_current_user as firebase_get_current_user

    return await firebase_get_current_user(request)


__all__ = [
    "AccessContext",
    "ToolPermissionDenied",
    "User",
    "auth_backend",
    "build_access_context",
    "can_access",
    "can_use_tool",
    "get_current_user",
]
