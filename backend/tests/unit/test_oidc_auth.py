from __future__ import annotations

import base64
import time

import jwt
import pytest

from auth.local_jwt import create_local_user
from auth.oidc import (
    decode_oidc_token,
    link_oidc_subject,
    oidc_config,
    reset_oidc_cache_for_testing,
    user_from_oidc_token,
)
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
    yield
    reset_oidc_cache_for_testing()
    reset_repository_for_testing(None)


def _secret_jwk(secret: bytes) -> dict:
    encoded = base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")
    return {"kty": "oct", "kid": "test-key", "alg": "HS256", "k": encoded}


def _token(secret: bytes, *, subject: str = "external-subject") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": subject,
            "iss": "https://idp.example.test",
            "aud": "platform-api",
            "iat": now,
            "exp": now + 300,
            "email": "attacker-controlled@example.net",
            "tenant_id": "attacker-tenant",
            "groupTags": ["aitana-admin"],
        },
        secret,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )


def test_oidc_config_defaults_discovery_and_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    config = oidc_config()
    assert config.audience == "platform-web"
    assert config.discovery_url == "https://idp.example.test/.well-known/openid-configuration"
    assert config.allowed_algorithms == ("HS256",)


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
