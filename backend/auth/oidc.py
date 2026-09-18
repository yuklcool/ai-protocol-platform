"""Optional OpenID Connect identity provider for self-hosted deployments.

OIDC is an authentication source only. Tenant, domain and role/group data are
reloaded from authoritative local auth_users records after token verification.

The browser flow uses Authorization Code + PKCE. The backend creates and stores
state/nonce/code-verifier transactions, exchanges the code server-side, verifies
the ID token, then returns that verified ID token to the browser as the bearer
credential for this platform session.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode, urlsplit

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
TRANSACTION_COLLECTION = "auth_oidc_transactions"
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


@dataclass(frozen=True)
class OidcBrowserConfig:
    redirect_uri: str
    scopes: tuple[str, ...]
    client_secret: str
    client_auth_method: str
    transaction_ttl_seconds: int


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


def oidc_browser_config() -> OidcBrowserConfig:
    redirect_uri = _required("OIDC_REDIRECT_URI")
    parsed_redirect = urlsplit(redirect_uri)
    if parsed_redirect.scheme not in {"http", "https"} or not parsed_redirect.netloc or parsed_redirect.fragment:
        raise RuntimeError("OIDC_REDIRECT_URI must be an absolute http(s) URL without a fragment")

    raw_scopes = os.environ.get("OIDC_SCOPES", "openid profile email").replace(",", " ")
    scopes = tuple(dict.fromkeys(part.strip() for part in raw_scopes.split() if part.strip()))
    if "openid" not in scopes:
        raise RuntimeError("OIDC_SCOPES must include openid")

    client_secret = os.environ.get("OIDC_CLIENT_SECRET", "").strip()
    default_method = "client_secret_basic" if client_secret else "none"
    method = os.environ.get("OIDC_CLIENT_AUTH_METHOD", "").strip().lower() or default_method
    if method not in {"none", "client_secret_basic", "client_secret_post"}:
        raise RuntimeError(
            "OIDC_CLIENT_AUTH_METHOD must be none, client_secret_basic, or client_secret_post"
        )
    if method != "none" and not client_secret:
        raise RuntimeError(f"OIDC_CLIENT_SECRET is required for {method}")

    raw_ttl = os.environ.get("OIDC_TRANSACTION_TTL_SECONDS", "300").strip()
    try:
        ttl = int(raw_ttl)
    except ValueError as exc:
        raise RuntimeError("OIDC_TRANSACTION_TTL_SECONDS must be an integer") from exc
    if ttl < 60 or ttl > 900:
        raise RuntimeError("OIDC_TRANSACTION_TTL_SECONDS must be between 60 and 900")

    return OidcBrowserConfig(
        redirect_uri=redirect_uri,
        scopes=scopes,
        client_secret=client_secret,
        client_auth_method=method,
        transaction_ttl_seconds=ttl,
    )


def validate_oidc_config() -> None:
    oidc_config()


def _subject_doc_id(issuer: str, subject: str) -> str:
    material = (_normalise_issuer(issuer) + "\n" + subject.strip()).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _transaction_doc_id(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _safe_return_to(value: str | None) -> str:
    candidate = (value or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return "/"
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return "/"
    return candidate


def _base64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


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


async def get_jwks(
    config: OidcConfig | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    config = config or oidc_config()
    discovery = await get_discovery(config)
    jwks_uri = str(discovery["jwks_uri"]).strip()

    async def load() -> dict[str, Any]:
        payload = await _fetch_json(jwks_uri)
        if not isinstance(payload.get("keys"), list):
            raise RuntimeError("OIDC JWKS response is missing keys")
        return payload

    if force_refresh:
        _jwks_cache.pop(jwks_uri, None)
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


async def decode_oidc_token(token: str, *, expected_nonce: str | None = None) -> dict[str, Any]:
    config = oidc_config()
    header = jwt.get_unverified_header(token)
    alg = str(header.get("alg") or "")
    if alg not in config.allowed_algorithms:
        raise jwt.InvalidTokenError("OIDC token algorithm is not allowed")
    kid = header.get("kid")
    if kid is not None and not isinstance(kid, str):
        raise jwt.InvalidTokenError("OIDC token kid is invalid")

    jwks = await get_jwks(config)
    try:
        key = _select_jwk(jwks, kid=kid, alg=alg)
    except jwt.InvalidTokenError:
        # A new kid commonly means the IdP rotated its signing key. Refresh the
        # cached JWKS once before failing the request.
        jwks = await get_jwks(config, force_refresh=True)
        key = _select_jwk(jwks, kid=kid, alg=alg)
    claims = jwt.decode(
        token,
        key=key,
        algorithms=[alg],
        issuer=config.issuer,
        audience=config.audience,
        options={"require": ["sub", "iss", "aud", "exp", "iat"]},
    )
    if expected_nonce is not None:
        actual_nonce = str(claims.get("nonce") or "")
        if not actual_nonce or not hmac.compare_digest(actual_nonce, expected_nonce):
            raise jwt.InvalidTokenError("OIDC nonce mismatch")
    return claims


async def user_from_oidc_token(token: str, *, expected_nonce: str | None = None) -> User:
    claims = await decode_oidc_token(token, expected_nonce=expected_nonce)
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise jwt.InvalidTokenError("OIDC token subject is missing")
    return _local_user_from_subject(issuer=str(claims.get("iss") or ""), subject=subject)


async def create_oidc_authorization_request(*, return_to: str = "/") -> dict[str, Any]:
    """Create one server-stored OIDC Authorization Code + PKCE transaction."""
    config = oidc_config()
    browser = oidc_browser_config()
    discovery = await get_discovery(config)
    authorization_endpoint = str(discovery.get("authorization_endpoint") or "").strip()
    token_endpoint = str(discovery.get("token_endpoint") or "").strip()
    if not authorization_endpoint or not token_endpoint:
        raise RuntimeError("OIDC discovery must provide authorization_endpoint and token_endpoint")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _base64url_sha256(code_verifier)
    now = int(time.time())
    expires_at = now + browser.transaction_ttl_seconds

    persistence.set_document(
        TRANSACTION_COLLECTION,
        _transaction_doc_id(state),
        {
            "issuer": config.issuer,
            "clientId": config.client_id,
            "nonce": nonce,
            "codeVerifier": code_verifier,
            "redirectUri": browser.redirect_uri,
            "returnTo": _safe_return_to(return_to),
            "createdAt": now,
            "expiresAt": expires_at,
        },
    )

    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": browser.redirect_uri,
            "scope": " ".join(browser.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    separator = "&" if "?" in authorization_endpoint else "?"
    return {
        "authorization_url": f"{authorization_endpoint}{separator}{query}",
        "expires_in": browser.transaction_ttl_seconds,
    }


def _consume_oidc_transaction(state: str) -> dict[str, Any]:
    state = state.strip()
    if not state:
        raise ValueError("OIDC state is required")
    doc_id = _transaction_doc_id(state)
    transaction = persistence.get_document(TRANSACTION_COLLECTION, doc_id)
    if transaction is None:
        raise ValueError("OIDC authorization state is invalid or expired")

    # Delete before the network exchange so a code/state pair can never be
    # replayed, even when the upstream token endpoint fails.
    persistence.delete_document(TRANSACTION_COLLECTION, doc_id)

    now = int(time.time())
    if int(transaction.get("expiresAt") or 0) < now:
        raise ValueError("OIDC authorization state is invalid or expired")

    config = oidc_config()
    browser = oidc_browser_config()
    if str(transaction.get("issuer") or "") != config.issuer:
        raise ValueError("OIDC authorization transaction issuer changed")
    if str(transaction.get("clientId") or "") != config.client_id:
        raise ValueError("OIDC authorization transaction client changed")
    if str(transaction.get("redirectUri") or "") != browser.redirect_uri:
        raise ValueError("OIDC authorization transaction redirect URI changed")
    return transaction


async def _exchange_authorization_code(
    *,
    code: str,
    transaction: dict[str, Any],
    discovery: dict[str, Any],
) -> dict[str, Any]:
    config = oidc_config()
    browser = oidc_browser_config()
    token_endpoint = str(discovery.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise RuntimeError("OIDC discovery is missing token_endpoint")

    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": str(transaction["redirectUri"]),
        "client_id": config.client_id,
        "code_verifier": str(transaction["codeVerifier"]),
    }
    auth: httpx.BasicAuth | None = None
    if browser.client_auth_method == "client_secret_post":
        data["client_secret"] = browser.client_secret
    elif browser.client_auth_method == "client_secret_basic":
        auth = httpx.BasicAuth(config.client_id, browser.client_secret)

    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            auth=auth,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OIDC token endpoint returned a non-object JSON payload")
    if not str(payload.get("id_token") or "").strip():
        raise RuntimeError("OIDC token endpoint did not return id_token")
    return payload


async def complete_oidc_authorization_code(*, code: str, state: str) -> dict[str, Any]:
    code = code.strip()
    if not code:
        raise ValueError("OIDC authorization code is required")

    transaction = _consume_oidc_transaction(state)
    discovery = await get_discovery()
    token_payload = await _exchange_authorization_code(
        code=code,
        transaction=transaction,
        discovery=discovery,
    )
    id_token = str(token_payload["id_token"]).strip()
    claims = await decode_oidc_token(id_token, expected_nonce=str(transaction["nonce"]))
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise jwt.InvalidTokenError("OIDC token subject is missing")
    user = _local_user_from_subject(
        issuer=str(claims.get("iss") or ""),
        subject=subject,
    )
    expires_in = max(1, int(claims["exp"]) - int(time.time()))
    return {
        "access_token": id_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "return_to": _safe_return_to(str(transaction.get("returnTo") or "/")),
        "user": user,
    }


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

    browser_configured = True
    browser_error = ""
    try:
        browser = oidc_browser_config()
    except RuntimeError as exc:
        browser_configured = False
        browser_error = str(exc)
        browser = None

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
            "authorizationCodePkce": browser_configured,
        },
    }
    if browser is not None:
        result["redirectUri"] = browser.redirect_uri
        result["scopes"] = list(browser.scopes)
        result["clientAuthMethod"] = browser.client_auth_method
    elif browser_error:
        result["browserFlowError"] = browser_error

    try:
        discovery = await get_discovery(config)
        result["reachable"] = True
        result["authorizationEndpoint"] = discovery.get("authorization_endpoint")
        result["tokenEndpoint"] = discovery.get("token_endpoint")
        result["endSessionEndpoint"] = discovery.get("end_session_endpoint")
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
    "OidcBrowserConfig",
    "OidcConfig",
    "SUBJECT_COLLECTION",
    "TRANSACTION_COLLECTION",
    "complete_oidc_authorization_code",
    "create_oidc_authorization_request",
    "decode_oidc_token",
    "get_current_user_oidc",
    "get_discovery",
    "get_jwks",
    "link_oidc_subject",
    "oidc_browser_config",
    "oidc_config",
    "oidc_provider_status",
    "reset_oidc_cache_for_testing",
    "user_from_oidc_token",
    "validate_oidc_config",
]
