"""Unified authentication entry point.

All business routes should continue importing ``get_current_user`` from this
module. The active verifier is selected by ``AUTH_BACKEND`` and every provider
returns the same trusted ``User`` / ``AccessContext`` shape.

Provider SDKs are imported lazily so Self-host/local-JWT startup does not pull
Firebase Admin into the core identity path.
"""

import logging

import jwt
from fastapi import HTTPException, Request

from auth.access_context import AccessContext, build_access_context, can_access
from auth.group_id_auth import AUTH_MODE as _GROUP_AUTH_MODE
from auth.group_id_auth import AnonymousGroupAuth, GroupRevoked, InvalidGroupToken
from auth.identity import auth_backend
from auth.models import User
from auth.permissions import ToolPermissionDenied, can_use_tool

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


async def get_current_user(request: Request) -> User:
    """Authenticate once, enforce deployment policy, and bind user tracing."""
    from auth.capability_access import refresh_authorization
    from observability.user_context import set_user_context

    user = refresh_authorization(await _resolve_user(request))
    request.state.access = build_access_context(user)
    set_user_context(user)
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
