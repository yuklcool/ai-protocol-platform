"""Built-in self-host identity provider backed by the platform Repository.

This provider deliberately reuses the existing persistence abstraction so the
self-host stack does not need a second auth database. Passwords are stored as
scrypt hashes and every authenticated request re-loads the authoritative user
record before constructing ``User``; tenant/domain/group tags are therefore
never trusted from browser-supplied claims.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, Request

from auth.access_context import build_access_context
from auth.firebase_auth import User
from db import persistence

logger = logging.getLogger(__name__)

AUTH_MODE = "local-jwt"
USER_COLLECTION = "auth_users"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def _normalise_email(email: str) -> str:
    return (email or "").strip().casefold()


def _domain_for_email(email: str) -> str:
    return email.rsplit("@", 1)[1] if "@" in email else ""


def _user_doc_id(email: str) -> str:
    return hashlib.sha256(_normalise_email(email).encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Return a self-describing scrypt password hash."""
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, hash_b64 = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _record_to_user(record: dict[str, Any]) -> User:
    email = _normalise_email(str(record.get("email") or ""))
    domain = str(record.get("domain") or _domain_for_email(email)).strip().lower()
    raw_tags = record.get("groupTags") or []
    return User(
        uid=str(record["uid"]),
        email=email,
        domain=domain,
        group_tags=frozenset(str(tag) for tag in raw_tags),
        auth_mode=AUTH_MODE,
    )


def get_local_user_by_email(email: str) -> dict[str, Any] | None:
    normalised = _normalise_email(email)
    if not normalised:
        return None
    return persistence.get_document(USER_COLLECTION, _user_doc_id(normalised))


def create_local_user(
    *,
    email: str,
    password: str,
    group_tags: set[str] | frozenset[str] | list[str] | tuple[str, ...] = (),
    uid: str | None = None,
    disabled: bool = False,
    overwrite: bool = False,
) -> User:
    """Create one local account using a deterministic email document key."""
    normalised = _normalise_email(email)
    if not normalised or "@" not in normalised:
        raise ValueError("a valid email address is required")
    doc_id = _user_doc_id(normalised)
    existing = persistence.get_document(USER_COLLECTION, doc_id)
    if existing is not None and not overwrite:
        raise ValueError("local user already exists")
    now = int(time.time())
    record = {
        "uid": uid or (str(existing.get("uid")) if existing else str(uuid.uuid4())),
        "email": normalised,
        "domain": _domain_for_email(normalised),
        "passwordHash": hash_password(password),
        "groupTags": sorted({str(tag).strip() for tag in group_tags if str(tag).strip()}),
        "disabled": bool(disabled),
        "createdAt": existing.get("createdAt", now) if existing else now,
        "updatedAt": now,
    }
    persistence.set_document(USER_COLLECTION, doc_id, record)
    return _record_to_user(record)


def authenticate_credentials(email: str, password: str) -> User | None:
    record = get_local_user_by_email(email)
    if record is None or bool(record.get("disabled")):
        return None
    password_hash = str(record.get("passwordHash") or "")
    if not password_hash or not verify_password(password, password_hash):
        return None
    return _record_to_user(record)


def _issuer() -> str:
    return os.environ.get("JWT_ISSUER", "ai-protocol-platform").strip() or "ai-protocol-platform"


def _audience() -> str:
    return os.environ.get("JWT_AUDIENCE", "ai-protocol-platform").strip() or "ai-protocol-platform"


def _expiry_seconds() -> int:
    raw = os.environ.get("JWT_EXPIRE_MINUTES", "60").strip()
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise RuntimeError("JWT_EXPIRE_MINUTES must be an integer") from exc
    if minutes < 5 or minutes > 10080:
        raise RuntimeError("JWT_EXPIRE_MINUTES must be between 5 and 10080")
    return minutes * 60


def _signing_key() -> str:
    key = os.environ.get("JWT_SIGNING_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SIGNING_KEY must be configured with at least 32 bytes")
    return key


def _verification_keys() -> list[str]:
    keys = [_signing_key()]
    for key in os.environ.get("JWT_PREVIOUS_SIGNING_KEYS", "").split(","):
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def issue_access_token(user: User) -> tuple[str, int]:
    now = int(time.time())
    expires_in = _expiry_seconds()
    payload = {
        "sub": user.uid,
        "email": user.email,
        "auth_mode": AUTH_MODE,
        "iss": _issuer(),
        "aud": _audience(),
        "iat": now,
        "nbf": now,
        "exp": now + expires_in,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256"), expires_in


def _decode_access_token(token: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for key in _verification_keys():
        try:
            return jwt.decode(
                token,
                key,
                algorithms=["HS256"],
                issuer=_issuer(),
                audience=_audience(),
                options={"require": ["sub", "email", "exp", "iat", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise
        except jwt.InvalidTokenError as exc:
            last_error = exc
    raise jwt.InvalidTokenError("token signature verification failed") from last_error


def user_from_token(token: str) -> User:
    """Verify the token, then resolve roles/domain from trusted persistence."""
    decoded = _decode_access_token(token)
    if decoded.get("auth_mode") != AUTH_MODE:
        raise jwt.InvalidTokenError("wrong auth mode")
    email = _normalise_email(str(decoded.get("email") or ""))
    record = get_local_user_by_email(email)
    if record is None or bool(record.get("disabled")):
        raise jwt.InvalidTokenError("local account is disabled or missing")
    if str(record.get("uid") or "") != str(decoded.get("sub") or ""):
        raise jwt.InvalidTokenError("subject does not match local account")
    return _record_to_user(record)


async def get_current_user_local_jwt(request: Request) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        user = user_from_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except (jwt.InvalidTokenError, RuntimeError) as exc:
        logger.info("auth: rejected local-jwt token (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    request.state.access = build_access_context(user)
    logger.info("auth: local-jwt uid=%s", user.uid)
    return user


@dataclass(frozen=True)
class LocalJwtIdentityProvider:
    async def get_current_user(self, request: Request) -> User:
        return await get_current_user_local_jwt(request)


__all__ = [
    "AUTH_MODE",
    "LocalJwtIdentityProvider",
    "authenticate_credentials",
    "create_local_user",
    "get_current_user_local_jwt",
    "get_local_user_by_email",
    "hash_password",
    "issue_access_token",
    "user_from_token",
    "verify_password",
]
