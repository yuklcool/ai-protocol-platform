"""Optional OpenID Connect identity provider for self-hosted deployments.

OIDC is an authentication source only. Tenant, domain and role/group data are
reloaded from authoritative local auth_users records after token verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
import jwt
from fastapi import HTTPException, Request

from auth.access_context import build_access_context
from auth.local_jwt import get_local_user_by_email
from auth.models import User
from db import persistence

logger = logging.getLogger(__name__)

AUTH_MODE = "oidc"
SUBJECT_COLLECTION = "auth_oidc_subjects"
_CACHE_TTL_SECONDS = 300
_cache_lock = asyncio.Lock()
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    audience: str
    client_id: str
    discovery_url: str
    allowed_algorithms: tuple[str, ...]


def _normalise_issuer(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured when AUTH_BACKEND=oidc")
    return value


def oidc_config() -> OidcConfig:
    issuer = _normalise_issuer(_required("OIDC_ISSUER"))
    client_id = _required("OIDC_CLIENT_ID")
    audience = os.environ.get("OIDC_AUDIENCE", "").strip() or client_id
    discovery_url = (
        os.environ.get("OIDC_DISCOVERY_URL", "").strip()
        or f"{issuer}/.well-known/openid-configuration"
    )
    algorithms = tuple(
        item.strip()
        for item in os.environ.get("OIDC_ALLOWED_ALGORITHMS", "RS256").split(",")
        if item.strip()
    )
    if not algorithms:
        raise RuntimeError("OIDC_ALLOWED_ALGORITHMS must contain at least one algorithm")
    if any(alg.lower() == "none" for alg in algorithms):
        raise RuntimeError("OIDC_ALLOWED_ALGORITHMS must not allow 'none'")
    return OidcConfig(
        issuer=issuer,
        audience=audience,
        client_id=client_id,
        discovery_url=discovery_url,
        allowed_algorithms=algorithms,
    )


def validate_oidc_config() -> None:
    oidc_config()


def _subject_doc_id(issuer: str, subject: str) -> str:
    material = (_normalise_issuer(issuer) + "\n" + subject.strip()).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def link_oidc_subject(*, issuer: str, subject: str, email: str, overwrite: bool = False) -> None:
    """Persist an explicit external subject to local-account mapping."""
    normalised_issuer = _normalise_issuer(issuer)
    subject = subject.strip()
    email = email.strip().casefold()
    if not normalised_issuer or not subject or "@" not in email:
        raise ValueError("issuer, subject and a valid local-user email are required")
    local = get_local_user_by_email(email)
    if local is None:
        raise ValueError("local user must exist before linking an OIDC subject")

    doc_id = _subject_doc_id(normalised_issuer, subject)
    existing = persistence.get_document(SUBJECT_COLLECTION, doc_id)
    if existing is not None and not overwrite:
        raise ValueError("OIDC subject is already linked")
    now = int(time.time())
    persistence.set_document(
        SUBJECT_COLLECTION,
        doc_id,
        {
            "issuer": normalised_issuer,
            "subject": subject,
            "email": email,
            "localUid": str(local.get("uid") or ""),
            "createdAt": existing.get("createdAt", now) if existing else now,
            "updatedAt": now,
        },
    )


def _local_user_from_subject(*, issuer: str, subject: str) -> User:
    mapping = persistence.get_document(SUBJECT_COLLECTION, _subject_doc_id(issuer, subject))
    if mapping is None:
        raise jwt.InvalidTokenError("OIDC subject is not linked to a local account")
    if _normalise_issuer(str(mapping.get("issuer") or "")) != _normalise_issuer(issuer):
        raise jwt.InvalidTokenError("OIDC issuer mapping mismatch")
    if str(mapping.get("subject") or "") != subject:
        raise jwt.InvalidTokenError("OIDC subject mapping mismatch")

    email = str(mapping.get("email") or "").strip().casefold()
    record = get_local_user_by_email(email)
    if record is None or bool(record.get("disabled")):
        raise jwt.InvalidTokenError("local account is disabled or missing")
    expected_uid = str(mapping.get("localUid") or "")
    if expected_uid and expected_uid != str(record.get("uid") or ""):
        raise jwt.InvalidTokenError("linked local account identity changed")

    domain = str(record.get("domain") or (email.rsplit("@", 1)[1] if "@" in email else "")).strip().lower()
    tenant_id = str(record.get("tenantId") or domain).strip()
    tags = frozenset(str(tag) for tag in (record.get("groupTags") or []))
    return User(
        uid=str(record.get("uid") or ""),
        email=email,
        domain=domain,
        tenant_id=tenant_id,
        group_tags=tags,
        auth_mode=AUTH_MODE,
    )


async def _fetch_json(url: str) -> dict[str, Any]:
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"OIDC endpoint returned a non-object JSON payload: {url}")
    return payload


async def _cached_json(
    cache: dict[str, tuple[float, dict[str, Any]]],
    key: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    now = time.monotonic()
    cached = cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    async with _cache_lock:
        cached = cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        payload = await loader()
        cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, payload)
        return payload


async def get_discovery(config: OidcConfig | None = None) -> dict[str, Any]:
    config = config or oidc_config()

    async def load() -> dict[str, Any]:
        payload = await _fetch_json(config.discovery_url)
        discovered_issuer = _normalise_issuer(str(payload.get("issuer") or ""))
        if discovered_issuer != config.issuer:
            raise RuntimeError("OIDC discovery issuer does not match OIDC_ISSUER")
        if not str(payload.get("jwks_uri") or "").strip():
            raise RuntimeError("OIDC discovery document is missing jwks_uri")
        return payload

    return await _cached_json(_discovery_cache, config.discovery_url, load)


async def get_jwks(config: OidcConfig | None = None) -> dict[str, Any]:
    config = config or oidc_config()
    discovery = await get_discovery(config)
    jwks_uri = str(discovery["jwks_uri"]).strip()

    async def load() -> dict[str, Any]:
        payload = await _fetch_json(jwks_uri)
        if not isinstance(payload.get("keys"), list):
            raise RuntimeError("OIDC JWKS response is missing keys")
        return payload

    return await _cached_json(_jwks_cache, jwks_uri, load)


def _select_jwk(jwks: dict[str, Any], *, kid: str | None, alg: str) -> Any:
    candidates: list[dict[str, Any]] = []
    for raw in jwks.get("keys") or []:
        if not isinstance(raw, dict):
            continue
        if kid and raw.get("kid") != kid:
            continue
        key_alg = str(raw.get("alg") or "")
        if key_alg and key_alg != alg:
            continue
        candidates.append(raw)
    if len(candidates) != 1:
        raise jwt.InvalidTokenError("unable to select a unique OIDC signing key")
    try:
        return jwt.PyJWK.from_dict(candidates[0], algorithm=alg).key
    except (jwt.PyJWKError, ValueError, TypeError) as exc:
        raise jwt.InvalidTokenError("invalid OIDC signing key") from exc


async def decode_oidc_token(token: str) -> dict[str, Any]:
    config = oidc_config()
    header = jwt.get_unverified_header(token)
    alg = str(header.get("alg") or "")
    if alg not in config.allowed_algorithms:
        raise jwt.InvalidTokenError("OIDC token algorithm is not allowed")
    kid = header.get("kid")
    if kid is not None and not isinstance(kid, str):
        raise jwt.InvalidTokenError("OIDC token kid is invalid")

    jwks = await get_jwks(config)
    key = _select_jwk(jwks, kid=kid, alg=alg)
    return jwt.decode(
        token,
        key=key,
        algorithms=[alg],
        issuer=config.issuer,
        audience=config.audience,
        options={"require": ["sub", "iss", "aud", "exp", "iat"]},
    )


async def user_from_oidc_token(token: str) -> User:
    claims = await decode_oidc_token(token)
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise jwt.InvalidTokenError("OIDC token subject is missing")
    return _local_user_from_subject(issuer=str(claims.get("iss") or ""), subject=subject)


async def get_current_user_oidc(request: Request) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        user = await user_from_oidc_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except (jwt.InvalidTokenError, httpx.HTTPError, RuntimeError) as exc:
        logger.info("auth: rejected oidc token (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    request.state.access = build_access_context(user)
    logger.info("auth: oidc uid=%s tenant=%s", user.uid, user.tenant_id or user.domain)
    return user


async def oidc_provider_status() -> dict[str, Any]:
    """Return non-secret provider capability/status information."""
    try:
        config = oidc_config()
    except RuntimeError as exc:
        return {"backend": "oidc", "configured": False, "error": str(exc)}

    result: dict[str, Any] = {
        "backend": "oidc",
        "configured": True,
        "issuer": config.issuer,
        "clientId": config.client_id,
        "audience": config.audience,
        "discoveryUrl": config.discovery_url,
        "allowedAlgorithms": list(config.allowed_algorithms),
        "capabilities": {
            "bearerVerification": True,
            "explicitSubjectMapping": True,
            "authorizationCodePkce": False,
        },
    }
    try:
        discovery = await get_discovery(config)
        result["reachable"] = True
        result["authorizationEndpoint"] = discovery.get("authorization_endpoint")
        result["tokenEndpoint"] = discovery.get("token_endpoint")
        result["jwksUri"] = discovery.get("jwks_uri")
    except (httpx.HTTPError, RuntimeError) as exc:
        result["reachable"] = False
        result["error"] = str(exc)
    return result


def reset_oidc_cache_for_testing() -> None:
    _discovery_cache.clear()
    _jwks_cache.clear()


__all__ = [
    "AUTH_MODE",
    "OidcConfig",
    "SUBJECT_COLLECTION",
    "decode_oidc_token",
    "get_current_user_oidc",
    "get_discovery",
    "get_jwks",
    "link_oidc_subject",
    "oidc_config",
    "oidc_provider_status",
    "reset_oidc_cache_for_testing",
    "user_from_oidc_token",
    "validate_oidc_config",
]
