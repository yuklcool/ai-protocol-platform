from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest

from auth.local_jwt import create_local_user
from auth.oidc import (
    TRANSACTION_COLLECTION,
    complete_oidc_authorization_code,
    create_oidc_authorization_request,
    decode_oidc_token,
    link_oidc_subject,
    oidc_browser_config,
    oidc_config,
    reset_oidc_cache_for_testing,
    user_from_oidc_token,
)
from db import persistence
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository


@pytest.fixture(autouse=True)
def isolated_oidc(monkeypatch: pytest.MonkeyPatch):
    reset_repository_for_testing(MemoryRepository())
    reset_oidc_cache_for_testing()
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.test")
    monkeypatch.setenv("OIDC_CLIENT_ID", "platform-web")
    monkeypatch.setenv("OIDC_AUDIENCE", "platform-api")
    monkeypatch.setenv("OIDC_ALLOWED_ALGORITHMS", "HS256")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/auth/oidc/callback")
    monkeypatch.setenv("OIDC_SCOPES", "openid profile email")
    monkeypatch.setenv("OIDC_TRANSACTION_TTL_SECONDS", "300")
    monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OIDC_CLIENT_AUTH_METHOD", "none")
    yield
    reset_oidc_cache_for_testing()
    reset_repository_for_testing(None)


def _secret_jwk(secret: bytes) -> dict:
    encoded = base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")
    return {"kty": "oct", "kid": "test-key", "alg": "HS256", "k": encoded}


def _token(
    secret: bytes,
    *,
    subject: str = "external-subject",
    nonce: str | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": "https://idp.example.test",
        "aud": "platform-api",
        "iat": now,
        "exp": now + 300,
        "email": "attacker-controlled@example.net",
        "tenant_id": "attacker-tenant",
        "groupTags": ["aitana-admin"],
    }
    if nonce is not None:
        payload["nonce"] = nonce
    return jwt.encode(
        payload,
        secret,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )


async def _fake_discovery(config=None) -> dict:
    return {
        "issuer": "https://idp.example.test",
        "authorization_endpoint": "https://idp.example.test/authorize",
        "token_endpoint": "https://idp.example.test/token",
        "jwks_uri": "https://idp.example.test/jwks",
    }


def _transaction_for_state(state: str) -> dict:
    doc_id = hashlib.sha256(state.encode("utf-8")).hexdigest()
    transaction = persistence.get_document(TRANSACTION_COLLECTION, doc_id)
    assert transaction is not None
    return transaction


def test_oidc_config_defaults_discovery_and_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    config = oidc_config()
    assert config.audience == "platform-web"
    assert config.discovery_url == "https://idp.example.test/.well-known/openid-configuration"
    assert config.allowed_algorithms == ("HS256",)


def test_oidc_browser_config_requires_openid_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_SCOPES", "profile email")
    with pytest.raises(RuntimeError, match="must include openid"):
        oidc_browser_config()


@pytest.mark.asyncio
async def test_verified_subject_maps_to_server_authoritative_local_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = create_local_user(
        email="owner@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
        group_tags={"tenant-admin:tenant-a"},
    )
    link_oidc_subject(
        issuer="https://idp.example.test/",
        subject="external-subject",
        email="owner@example.com",
    )

    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"

    async def fake_get_jwks(config=None):
        return {"keys": [_secret_jwk(secret)]}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    user = await user_from_oidc_token(_token(secret))

    assert user.uid == local.uid
    assert user.email == "owner@example.com"
    assert user.tenant_id == "tenant-a"
    assert user.group_tags == frozenset({"tenant-admin:tenant-a"})
    assert user.auth_mode == "oidc"
    assert user.tenant_id != "attacker-tenant"
    assert "aitana-admin" not in user.group_tags


@pytest.mark.asyncio
async def test_unlinked_subject_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"

    async def fake_get_jwks(config=None):
        return {"keys": [_secret_jwk(secret)]}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    with pytest.raises(jwt.InvalidTokenError, match="not linked"):
        await user_from_oidc_token(_token(secret, subject="not-linked"))


@pytest.mark.asyncio
async def test_disabled_local_user_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    create_local_user(
        email="owner@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
    )
    link_oidc_subject(
        issuer="https://idp.example.test",
        subject="external-subject",
        email="owner@example.com",
    )
    create_local_user(
        email="owner@example.com",
        password="another strong password",
        tenant_id="tenant-a",
        disabled=True,
        overwrite=True,
    )

    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"

    async def fake_get_jwks(config=None):
        return {"keys": [_secret_jwk(secret)]}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    with pytest.raises(jwt.InvalidTokenError, match="disabled"):
        await user_from_oidc_token(_token(secret))


@pytest.mark.asyncio
async def test_algorithm_allowlist_rejects_unconfigured_algorithm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OIDC_ALLOWED_ALGORITHMS", "RS256")
    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"
    with pytest.raises(jwt.InvalidTokenError, match="algorithm"):
        await decode_oidc_token(_token(secret))


def test_none_algorithm_can_never_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ALLOWED_ALGORITHMS", "RS256,none")
    with pytest.raises(RuntimeError, match="must not allow"):
        oidc_config()


@pytest.mark.asyncio
async def test_authorization_request_stores_pkce_transaction_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("auth.oidc.get_discovery", _fake_discovery)

    result = await create_oidc_authorization_request(return_to="/skills?tab=mine")
    parsed = urlsplit(result["authorization_url"])
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "idp.example.test"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["platform-web"]
    assert query["redirect_uri"] == ["https://app.example.test/auth/oidc/callback"]
    assert query["scope"] == ["openid profile email"]
    assert query["code_challenge_method"] == ["S256"]

    state = query["state"][0]
    nonce = query["nonce"][0]
    transaction = _transaction_for_state(state)
    verifier = str(transaction["codeVerifier"])
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")

    assert transaction["nonce"] == nonce
    assert transaction["returnTo"] == "/skills?tab=mine"
    assert query["code_challenge"] == [expected_challenge]
    assert verifier not in result["authorization_url"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "return_to",
    [
        "https://evil.example/steal",
        "//evil.example/steal",
        "/\\\\evil.example/steal",
    ],
)
async def test_authorization_request_blocks_external_return_url(
    monkeypatch: pytest.MonkeyPatch,
    return_to: str,
) -> None:
    monkeypatch.setattr("auth.oidc.get_discovery", _fake_discovery)
    result = await create_oidc_authorization_request(return_to=return_to)
    state = parse_qs(urlsplit(result["authorization_url"]).query)["state"][0]
    assert _transaction_for_state(state)["returnTo"] == "/"


@pytest.mark.asyncio
async def test_callback_verifies_nonce_and_consumes_state_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = create_local_user(
        email="owner@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
        group_tags={"tenant-admin:tenant-a"},
    )
    link_oidc_subject(
        issuer="https://idp.example.test",
        subject="external-subject",
        email="owner@example.com",
    )
    monkeypatch.setattr("auth.oidc.get_discovery", _fake_discovery)

    start = await create_oidc_authorization_request(return_to="/chat")
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    transaction = _transaction_for_state(state)
    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"
    id_token = _token(secret, nonce=str(transaction["nonce"]))

    async def fake_get_jwks(config=None):
        return {"keys": [_secret_jwk(secret)]}

    async def fake_exchange(*, code, transaction, discovery):
        assert code == "authorization-code"
        assert transaction["codeVerifier"]
        assert discovery["token_endpoint"].endswith("/token")
        return {"id_token": id_token}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    monkeypatch.setattr("auth.oidc._exchange_authorization_code", fake_exchange)

    result = await complete_oidc_authorization_code(code="authorization-code", state=state)
    assert result["user"].uid == local.uid
    assert result["user"].tenant_id == "tenant-a"
    assert result["return_to"] == "/chat"
    assert result["access_token"] == id_token

    with pytest.raises(ValueError, match="invalid or expired"):
        await complete_oidc_authorization_code(code="authorization-code", state=state)


@pytest.mark.asyncio
async def test_callback_rejects_nonce_mismatch_and_still_consumes_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_local_user(
        email="owner@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
    )
    link_oidc_subject(
        issuer="https://idp.example.test",
        subject="external-subject",
        email="owner@example.com",
    )
    monkeypatch.setattr("auth.oidc.get_discovery", _fake_discovery)

    start = await create_oidc_authorization_request()
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    secret = b"test-secret-that-is-longer-than-thirty-two-bytes"

    async def fake_get_jwks(config=None):
        return {"keys": [_secret_jwk(secret)]}

    async def fake_exchange(*, code, transaction, discovery):
        return {"id_token": _token(secret, nonce="wrong-nonce")}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    monkeypatch.setattr("auth.oidc._exchange_authorization_code", fake_exchange)

    with pytest.raises(jwt.InvalidTokenError, match="nonce mismatch"):
        await complete_oidc_authorization_code(code="authorization-code", state=state)
    with pytest.raises(ValueError, match="invalid or expired"):
        await complete_oidc_authorization_code(code="authorization-code", state=state)


@pytest.mark.asyncio
async def test_unknown_kid_refreshes_jwks_once(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = b"rotated-secret-that-is-longer-than-thirty-two-bytes"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "external-subject",
            "iss": "https://idp.example.test",
            "aud": "platform-api",
            "iat": now,
            "exp": now + 300,
        },
        secret,
        algorithm="HS256",
        headers={"kid": "rotated-key"},
    )
    calls: list[bool] = []

    async def fake_get_jwks(config=None, *, force_refresh=False):
        calls.append(force_refresh)
        if force_refresh:
            rotated = _secret_jwk(secret)
            rotated["kid"] = "rotated-key"
            return {"keys": [rotated]}
        stale = _secret_jwk(b"old-secret-that-is-longer-than-thirty-two-bytes")
        stale["kid"] = "old-key"
        return {"keys": [stale]}

    monkeypatch.setattr("auth.oidc.get_jwks", fake_get_jwks)
    claims = await decode_oidc_token(token)
    assert claims["sub"] == "external-subject"
    assert calls == [False, True]
