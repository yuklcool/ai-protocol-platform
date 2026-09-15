"""Firebase/Identity Platform identity provider adapter.

This module is intentionally provider-specific. Core Self-host auth code should
import ``User`` from ``auth.models``. The Firebase Admin SDK itself is imported
only when a Firebase verifier/lookup is actually executed, so legacy modules
that still import ``User`` from this compatibility adapter do not pull Firebase
into a local-JWT startup.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException, Request

from auth.access_context import build_access_context
from auth.models import User

logger = logging.getLogger(__name__)


def _firebase_auth_api():
    """Load Firebase Admin only for the Firebase provider execution path."""
    from firebase_admin import auth as fb_auth

    return fb_auth


def _extract_domain(email: str) -> str:
    """Return the part of ``email`` after ``@``, or empty string."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1]


def _tenant_id_from_claims(claims: dict[str, Any], domain: str) -> str:
    """Resolve a trusted stable tenant id with legacy domain fallback.

    Both ``tenant_id`` and ``tenantId`` are accepted so OIDC-style custom
    claims and existing camelCase platform records can converge on the same
    provider-neutral ``User.tenant_id`` field. Firebase has already verified
    these claims before this function is called.
    """
    explicit = claims.get("tenant_id") or claims.get("tenantId")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    return domain


def _user_from_decoded_token(decoded: dict[str, Any]) -> User:
    """Build the provider-neutral ``User`` from a verified Firebase token."""
    email = decoded.get("email") or ""
    domain = _extract_domain(email)
    raw_tags = decoded.get("groupTags") or []
    group_tags = frozenset(str(t) for t in raw_tags)
    return User(
        uid=decoded["uid"],
        email=email,
        domain=domain,
        tenant_id=_tenant_id_from_claims(decoded, domain),
        group_tags=group_tags,
        auth_mode="firebase",
    )


async def get_current_user(request: Request) -> User:
    """Verify ``Authorization: Bearer <firebase-id-token>``."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Malformed Authorization header")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    fb_auth = _firebase_auth_api()
    try:
        decoded = fb_auth.verify_id_token(token)
    except fb_auth.ExpiredIdTokenError as exc:
        logger.info("auth: rejected expired token")
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except fb_auth.InvalidIdTokenError as exc:
        logger.info("auth: rejected invalid token")
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except Exception as exc:
        logger.info("auth: rejected token (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = _apply_derived_group_tags(_user_from_decoded_token(decoded))
    request.state.access = build_access_context(user)
    logger.info("auth: authenticated uid=%s tenant=%s", user.uid, user.tenant_id or user.domain)
    return user


def _apply_derived_group_tags(user: User) -> User:
    """Union trusted per-domain derived tags into ``user.group_tags``."""
    if not user.domain:
        return user
    from db.clients import resolve_derived_group_tags

    try:
        derived = resolve_derived_group_tags(user.domain)
    except Exception as exc:
        logger.warning("auth: derived-group-tags lookup failed (%s)", type(exc).__name__)
        return user
    if not derived:
        return user
    return user.model_copy(update={"group_tags": user.group_tags | derived})


# --- authoritative lookup for non-JWT Firebase callers (channels) ----------

_USER_CACHE_TTL_SEC = 60.0
_user_cache: dict[str, tuple[float, User | None]] = {}


def clear_user_cache() -> None:
    """Drop the Firebase resolve-by-UID cache."""
    _user_cache.clear()


def resolve_user_by_uid(uid: str) -> User | None:
    """Build an authoritative ``User`` from the Firebase account record."""
    now = time.monotonic()
    cached = _user_cache.get(uid)
    if cached is not None and now - cached[0] < _USER_CACHE_TTL_SEC:
        return cached[1]

    fb_auth = _firebase_auth_api()
    user: User | None
    try:
        record = fb_auth.get_user(uid)
    except Exception as exc:
        logger.warning("auth: resolve_user_by_uid(%s) failed (%s)", uid, type(exc).__name__)
        user = None
    else:
        email = getattr(record, "email", None) or ""
        domain = _extract_domain(email)
        claims = getattr(record, "custom_claims", None) or {}
        raw_tags = claims.get("groupTags") or []
        try:
            group_tags = frozenset(str(t) for t in raw_tags)
        except TypeError:
            logger.warning("auth: uid=%s has a non-iterable groupTags claim; ignoring", uid)
            group_tags = frozenset()
        user = _apply_derived_group_tags(
            User(
                uid=uid,
                email=email,
                domain=domain,
                tenant_id=_tenant_id_from_claims(claims, domain),
                group_tags=group_tags,
                auth_mode="firebase",
            )
        )

    _user_cache[uid] = (now, user)
    return user


# Compatibility re-export: legacy provider-specific imports continue to work,
# but new core/runtime modules must import User from auth.models.
__all__ = ["User", "clear_user_cache", "get_current_user", "resolve_user_by_uid"]