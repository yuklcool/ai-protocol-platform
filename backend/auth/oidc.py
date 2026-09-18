"""Generic OpenID Connect identity provider for self-hosted deployments.

The OIDC provider authenticates an external subject, but authorization remains
server-authoritative.  Tenant id, group tags and local uid are always loaded
from the platform's persisted `auth_users` record; browser/token claims are
never used directly as role or tenant truth.

Browser flow:
    Authorization Code + PKCE -> /api/auth/oidc/exchange -> verified ID token
    -> browser stores the ID token -> normal Authorization: Bearer requests.

The exchange endpoint never returns the upstream access/refresh token.  The
verified OIDC ID token is sufficient for this platform's identity boundary and
keeps the first implementation intentionally small.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import HTTPException, Request

from auth.access_context import build_access_context
from auth.local_jwt import get_local_user_by_email, user_from_local_record
from auth.models import User
from db import persistence

logger = logging.getLogger(__name__)

AUTH_MODE = "oidc"
OIDC_LINK_COLLECTION = "auth_oidc_links"
_DEFAULT_SCOPES = ("openid", "profile", "email")
_DEFAULT_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384")
_PKCE_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")

_discovery_cache: tuple[str, float, dict[str, Any]] | None = None
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class OidcSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...]
    email_claim: str
    require_email_verified: bool
    allow_insecure_http: bool
    allowed_algorithms: tuple[str, ...]
    discovery_ttl_seconds: int
    jwks_ttl_seconds: int
    http_timeout_seconds: float
    clock_skew_seconds: int


class OidcConfigurationError(RuntimeError):
    """Deployment OIDC configuration is missing or unsafe."""


class OidcProtocolError(RuntimeError):
    """The configured provider returned an invalid OIDC response."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise OidcConfigurationError(f"{name} must be a boolean")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise OidcConfigurationError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise OidcConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise OidcConfigurationError(f"{name} must be a number") from exc
    if value < minimum or value > maximum:
        raise OidcConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def oidc_settings() -> OidcSettings:
    issuer = os.environ.get("OIDC_ISSUER", "").strip()
    client_id = os.environ.get("OIDC_CLIENT_ID", "").strip()
    redirect_uri = os.environ.get("OIDC_REDIRECT_URI", "").strip()
    missing = [
        name
        for name, value in (
            ("OIDC_ISSUER", issuer),
            ("OIDC_CLIENT_ID", client_id),
            ("OIDC_REDIRECT_URI", redirect_uri),
        )
        if not value
    ]
    if missing:
        raise OidcConfigurationError("Missing required OIDC configuration: " + ", ".join(missing))

    scopes = tuple(part for part in os.environ.get("OIDC_SCOPES", " ".join(_DEFAULT_SCOPES)).split() if part)
    if "openid" not in scopes:
        raise OidcConfigurationError("OIDC_SCOPES must include openid")

    algorithms = tuple(
        part.strip()
        for part in os.environ.get("OIDC_ALLOWED_ALGORITHMS", ",".join(_DEFAULT_ALGORITHMS)).split(",")
        if part.strip()
    )
    if not algorithms:
        raise OidcConfigurationError("OIDC_ALLOWED_ALGORITHMS must not be empty")
    if any(alg.lower() == "none" or alg.upper().startswith("HS") for alg in algorithms):
        raise OidcConfigurationError("OIDC_ALLOWED_ALGORITHMS may not enable none or HMAC algorithms")

    settings = OidcSettings(
        issuer=issuer,
        client_id=client_id,
        client_secret=os.environ.get("OIDC_CLIENT_SECRET", "").strip(),
        redirect_uri=redirect_uri,
        scopes=scopes,
        email_claim=os.environ.get("OIDC_EMAIL_CLAIM", "email").strip() or "email",
        require_email_verified=_env_bool("OIDC_REQUIRE_EMAIL_VERIFIED", True),
        allow_insecure_http=_env_bool("OIDC_ALLOW_INSECURE_HTTP", False),
        allowed_algorithms=algorithms,
        discovery_ttl_seconds=_env_int("OIDC_DISCOVERY_TTL_SECONDS", 300, minimum=30, maximum=86400),
        jwks_ttl_seconds=_env_int("OIDC_JWKS_TTL_SECONDS", 300, minimum=30, maximum=86400),
        http_timeout_seconds=_env_float("OIDC_HTTP_TIMEOUT_SECONDS", 10.0, minimum=1.0, maximum=60.0),
        clock_skew_seconds=_env_int("OIDC_CLOCK_SKEW_SECONDS", 60, minimum=0, maximum=600),
    )
    _validate_url(settings.issuer, "OIDC_ISSUER", settings.allow_insecure_http)
    _validate_url(settings.redirect_uri, "OIDC_REDIRECT_URI", True, allow_custom_scheme=False)
    return settings


def _validate_url(
    value: str,
    label: str,
    allow_insecure_http: bool,
    *,
    allow_custom_scheme: bool = False,
) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise OidcConfigurationError(f"{label} must be an absolute URL")
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and allow_insecure_http:
        return
    if allow_custom_scheme:
        return
    raise OidcConfigurationError(f"{label} must use https (set OIDC_ALLOW_INSECURE_HTTP=1 only for trusted dev IdPs)")


def clear_oidc_cache() -> None:
    """Clear discovery/JWKS caches (primarily for tests and config reloads)."""
    global _discovery_cache
    _discovery_cache = None
    _jwks_cache.clear()


async def _fetch_json(url: str, settings: OidcSettings) -> dict[str, Any]:
    _validate_url(url, "OIDC provider endpoint", settings.allow_insecure_http)
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcProtocolError("OIDC provider request failed") from exc
    if not isinstance(payload, dict):
        raise OidcProtocolError("OIDC provider returned a non-object JSON response")
    return payload


async def get_oidc_discovery(*, force_refresh: bool = False) -> dict[str, Any]:
    global _discovery_cache
    settings = oidc_settings()
    now = time.monotonic()
    if (
        not force_refresh
        and _discovery_cache is not None
        and _discovery_cache[0] == settings.issuer
        and now - _discovery_cache[1] < settings.discovery_ttl_seconds
    ):
        return _discovery_cache[2]

    discovery_url = f"{settings.issuer.rstrip('/')}/.well-known/openid-configuration"
    metadata = await _fetch_json(discovery_url, settings)
    if metadata.get("issuer") != settings.issuer:
        raise OidcProtocolError("OIDC discovery issuer does not match OIDC_ISSUER")

    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value:
            raise OidcProtocolError(f"OIDC discovery is missing {field}")
        _validate_url(value, field, settings.allow_insecure_http)

    _discovery_cache = (settings.issuer, now, metadata)
    return metadata


async def _get_jwks(jwks_uri: str, *, force_refresh: bool = False) -> dict[str, Any]:
    settings = oidc_settings()
    now = time.monotonic()
    cached = _jwks_cache.get(jwks_uri)
    if not force_refresh and cached is not None and now - cached[0] < settings.jwks_ttl_seconds:
        return cached[1]

    jwks = await _fetch_json(jwks_uri, settings)
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise OidcProtocolError("OIDC JWKS response is missing keys")
    _jwks_cache[jwks_uri] = (now, jwks)
    return jwks


def _select_jwk(jwks: dict[str, Any], *, kid: str | None, alg: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for raw in jwks.get("keys", []):
        if not isinstance(raw, dict):
            continue
        if raw.get("use") not in (None, "sig"):
            continue
        if raw.get("alg") not in (None, alg):
            continue
        if kid is not None and raw.get("kid") != kid:
            continue
        candidates.append(raw)
    if kid is None:
        return candidates[0] if len(candidates) == 1 else None
    return candidates[0] if candidates else None


async def verify_oidc_id_token(token: str, *, nonce: str | None = None) -> dict[str, Any]:
    """Verify signature, issuer, audience, expiry and optional OIDC nonce."""
    settings = oidc_settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise jwt.InvalidTokenError("invalid OIDC token header") from exc

    alg = str(header.get("alg") or "")
    if alg not in settings.allowed_algorithms:
        raise jwt.InvalidAlgorithmError("OIDC token algorithm is not allowed")
    kid_raw = header.get("kid")
    kid = str(kid_raw) if kid_raw is not None else None

    discovery = await get_oidc_discovery()
    jwks_uri = str(discovery["jwks_uri"])
    jwks = await _get_jwks(jwks_uri)
    jwk = _select_jwk(jwks, kid=kid, alg=alg)
    if jwk is None:
        # A signing-key rotation may publish a new kid before our cache expires.
        jwks = await _get_jwks(jwks_uri, force_refresh=True)
        jwk = _select_jwk(jwks, kid=kid, alg=alg)
    if jwk is None:
        raise jwt.InvalidKeyError("No matching OIDC signing key")

    try:
        signing_key = jwt.PyJWK.from_dict(jwk, algorithm=alg).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            issuer=settings.issuer,
            audience=settings.client_id,
            leeway=settings.clock_skew_seconds,
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise jwt.InvalidTokenError("OIDC ID token validation failed") from exc

    audience = claims.get("aud")
    if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != settings.client_id:
        raise jwt.InvalidAudienceError("OIDC azp does not match client id")

    if nonce is not None:
        actual = str(claims.get("nonce") or "")
        if not actual or not hmac.compare_digest(actual, nonce):
            raise jwt.InvalidTokenError("OIDC nonce mismatch")
    return claims


def _normalise_email(value: str) -> str:
    return (value or "").strip().casefold()


def _subject_link_id(issuer: str, subject: str) -> str:
    raw = f"subject\0{issuer}\0{subject}".encode()
    return hashlib.sha256(raw).hexdigest()


def _user_link_id(issuer: str, uid: str) -> str:
    raw = f"user\0{issuer}\0{uid}".encode()
    return hashlib.sha256(raw).hexdigest()


def _record_to_oidc_user(record: dict[str, Any]) -> User:
    return user_from_local_record(record).model_copy(update={"auth_mode": AUTH_MODE})


def _load_linked_user(settings: OidcSettings, subject: str) -> User | None:
    link = persistence.get_document(OIDC_LINK_COLLECTION, _subject_link_id(settings.issuer, subject))
    if link is None:
        return None
    if str(link.get("issuer") or "") != settings.issuer or str(link.get("subject") or "") != subject:
        raise HTTPException(status_code=403, detail="OIDC identity link is invalid")
    email = _normalise_email(str(link.get("email") or ""))
    record = get_local_user_by_email(email)
    if record is None or bool(record.get("disabled")):
        raise HTTPException(status_code=403, detail="OIDC account is not provisioned")
    if str(record.get("uid") or "") != str(link.get("uid") or ""):
        raise HTTPException(status_code=403, detail="OIDC identity link no longer matches the local account")
    return _record_to_oidc_user(record)


def resolve_oidc_user(claims: dict[str, Any]) -> User:
    """Map a verified external subject onto the authoritative local user row."""
    settings = oidc_settings()
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="OIDC token is missing subject")

    linked = _load_linked_user(settings, subject)
    if linked is not None:
        return linked

    email = _normalise_email(str(claims.get(settings.email_claim) or ""))
    if not email or "@" not in email:
        raise HTTPException(status_code=403, detail="OIDC account does not provide a usable email")

    if settings.require_email_verified and claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="OIDC email is not verified")

    record = get_local_user_by_email(email)
    if record is None or bool(record.get("disabled")):
        # Deliberately do not auto-create users. Tenant/roles must be provisioned
        # in PostgreSQL first so the IdP never becomes an authorization source.
        raise HTTPException(status_code=403, detail="OIDC account is not provisioned")
    user = _record_to_oidc_user(record)

    reverse_id = _user_link_id(settings.issuer, user.uid)
    existing_reverse = persistence.get_document(OIDC_LINK_COLLECTION, reverse_id)
    if existing_reverse is not None and str(existing_reverse.get("subject") or "") != subject:
        raise HTTPException(status_code=403, detail="Local account is already linked to a different OIDC subject")

    now = int(time.time())
    link = {
        "issuer": settings.issuer,
        "subject": subject,
        "uid": user.uid,
        "email": user.email,
        "createdAt": now,
    }
    persistence.set_document(OIDC_LINK_COLLECTION, _subject_link_id(settings.issuer, subject), link)
    persistence.set_document(OIDC_LINK_COLLECTION, reverse_id, link)
    return user


async def get_current_user_oidc(request: Request) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = await verify_oidc_id_token(token)
        user = resolve_oidc_user(claims)
    except HTTPException:
        raise
    except (jwt.PyJWTError, OidcConfigurationError, OidcProtocolError) as exc:
        logger.info("auth: rejected oidc token (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    request.state.access = build_access_context(user)
    logger.info("auth: oidc uid=%s tenant=%s", user.uid, user.tenant_id or user.domain)
    return user


async def public_oidc_configuration() -> dict[str, Any]:
    settings = oidc_settings()
    discovery = await get_oidc_discovery()
    return {
        "issuer": settings.issuer,
        "clientId": settings.client_id,
        "redirectUri": settings.redirect_uri,
        "scopes": list(settings.scopes),
        "authorizationEndpoint": discovery["authorization_endpoint"],
    }


async def exchange_authorization_code(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    nonce: str,
) -> tuple[str, int, User]:
    """Exchange one PKCE code and return only the verified ID token + local user."""
    settings = oidc_settings()
    if not code.strip():
        raise HTTPException(status_code=400, detail="Missing OIDC authorization code")
    if not _PKCE_RE.fullmatch(code_verifier):
        raise HTTPException(status_code=400, detail="Invalid PKCE code verifier")
    if redirect_uri != settings.redirect_uri:
        raise HTTPException(status_code=400, detail="OIDC redirect URI does not match deployment configuration")
    if len(nonce) < 16 or len(nonce) > 512:
        raise HTTPException(status_code=400, detail="Invalid OIDC nonce")

    discovery = await get_oidc_discovery()
    token_endpoint = str(discovery["token_endpoint"])
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "code_verifier": code_verifier,
    }
    if settings.client_secret:
        data["client_secret"] = settings.client_secret

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, follow_redirects=False) as client:
            response = await client.post(
                token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("auth: OIDC code exchange failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="OIDC authorization code exchange failed") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="OIDC token endpoint returned an invalid response")
    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise HTTPException(status_code=401, detail="OIDC token response did not include an ID token")

    try:
        claims = await verify_oidc_id_token(id_token, nonce=nonce)
        user = resolve_oidc_user(claims)
    except HTTPException:
        raise
    except (jwt.PyJWTError, OidcConfigurationError, OidcProtocolError) as exc:
        raise HTTPException(status_code=401, detail="OIDC ID token validation failed") from exc

    now = int(time.time())
    exp = int(claims.get("exp") or now)
    expires_in = max(1, exp - now)
    return id_token, expires_in, user


__all__ = [
    "AUTH_MODE",
    "OIDC_LINK_COLLECTION",
    "OidcConfigurationError",
    "OidcProtocolError",
    "OidcSettings",
    "clear_oidc_cache",
    "exchange_authorization_code",
    "get_current_user_oidc",
    "get_oidc_discovery",
    "oidc_settings",
    "public_oidc_configuration",
    "resolve_oidc_user",
    "verify_oidc_id_token",
]
