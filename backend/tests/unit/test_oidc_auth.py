from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from auth.local_jwt import authenticate_credentials, create_local_user, get_local_user_by_email
from auth.oidc import (
    OidcConfigurationError,
    clear_oidc_cache,
    exchange_authorization_code,
    get_current_user_oidc,
    get_oidc_discovery,
    oidc_settings,
    resolve_oidc_user,
)
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository


@pytest.fixture(autouse=True)
def isolated_oidc(monkeypatch: pytest.MonkeyPatch):
    reset_repository_for_testing(MemoryRepository())
    monkeypatch.setenv("OIDC_ISSUER", "https://id.example.com/realms/platform")
    monkeypatch.setenv("OIDC_CLIENT_ID", "ai-protocol-platform")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://localhost:3456/auth/oidc/callback")
    monkeypatch.setenv("OIDC_SCOPES", "openid profile email")
    monkeypatch.setenv("OIDC_REQUIRE_EMAIL_VERIFIED", "true")
    monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OIDC_ALLOW_INSECURE_HTTP", raising=False)
    monkeypatch.delenv("SELFHOST_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SELFHOST_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("AUTH_BACKEND", raising=False)
    clear_oidc_cache()
    yield
    clear_oidc_cache()
    reset_repository_for_testing(None)


def _claims(*, subject: str = "subject-1", email: str = "admin@example.com") -> dict:
    now = int(time.time())
    return {
        "sub": subject,
        "iss": "https://id.example.com/realms/platform",
        "aud": "ai-protocol-platform",
        "iat": now,
        "exp": now + 3600,
        "email": email,
        "email_verified": True,
        # These authorization-looking claims must be ignored.
        "tenant_id": "attacker-tenant",
        "groupTags": ["aitana-admin"],
    }




def test_external_identity_record_cannot_use_password_login() -> None:
    from auth.local_jwt import create_external_identity_user

    user = create_external_identity_user(
        email="sso-admin@example.com",
        tenant_id="tenant-sso",
        group_tags={"aitana-admin"},
    )
    record = get_local_user_by_email("sso-admin@example.com")
    assert record is not None
    assert "passwordHash" not in record
    assert user.tenant_id == "tenant-sso"
    assert authenticate_credentials("sso-admin@example.com", "any password at all") is None


def test_oidc_selfhost_bootstrap_creates_first_passwordless_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.seed_selfhost_admin import main

    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.setenv("SELFHOST_ADMIN_EMAIL", "first-admin@example.com")

    assert main() == 0
    record = get_local_user_by_email("first-admin@example.com")
    assert record is not None
    assert "passwordHash" not in record
    assert "aitana-admin" in set(record.get("groupTags") or [])
    assert authenticate_credentials("first-admin@example.com", "irrelevant password") is None

    # Idempotent restart must not replace the stable local uid or identity data.
    first_uid = record["uid"]
    assert main() == 0
    assert get_local_user_by_email("first-admin@example.com")["uid"] == first_uid


def test_oidc_settings_rejects_unsafe_algorithms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ALLOWED_ALGORITHMS", "RS256,HS256")
    with pytest.raises(OidcConfigurationError, match="HMAC"):
        oidc_settings()


@pytest.mark.asyncio
async def test_discovery_is_cached_and_validates_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_fetch(url: str, settings):  # type: ignore[no-untyped-def]
        calls.append(url)
        return {
            "issuer": settings.issuer,
            "authorization_endpoint": "https://id.example.com/authorize",
            "token_endpoint": "https://id.example.com/token",
            "jwks_uri": "https://id.example.com/jwks",
        }

    monkeypatch.setattr("auth.oidc._fetch_json", fake_fetch)
    first = await get_oidc_discovery()
    second = await get_oidc_discovery()
    assert first == second
    assert len(calls) == 1

    clear_oidc_cache()

    async def wrong_issuer(url: str, settings):  # type: ignore[no-untyped-def]
        del url, settings
        return {
            "issuer": "https://evil.example.com",
            "authorization_endpoint": "https://id.example.com/authorize",
            "token_endpoint": "https://id.example.com/token",
            "jwks_uri": "https://id.example.com/jwks",
        }

    monkeypatch.setattr("auth.oidc._fetch_json", wrong_issuer)
    with pytest.raises(RuntimeError, match="issuer"):
        await get_oidc_discovery()


def test_oidc_mapping_uses_local_tenant_and_roles_not_token_claims() -> None:
    local = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
        group_tags={"tenant-admin:tenant-a"},
    )

    user = resolve_oidc_user(_claims())
    assert user.uid == local.uid
    assert user.tenant_id == "tenant-a"
    assert user.group_tags == frozenset({"tenant-admin:tenant-a"})
    assert "aitana-admin" not in user.group_tags
    assert user.auth_mode == "oidc"


def test_oidc_subject_link_survives_claim_email_change() -> None:
    local = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
    )
    first = resolve_oidc_user(_claims())
    assert first.uid == local.uid

    linked = resolve_oidc_user(_claims(email="renamed@example.net"))
    assert linked.uid == local.uid
    assert linked.email == "admin@example.com"


def test_oidc_rejects_second_subject_for_same_local_user() -> None:
    create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
    )
    resolve_oidc_user(_claims(subject="subject-1"))

    with pytest.raises(HTTPException, match="different OIDC subject"):
        resolve_oidc_user(_claims(subject="subject-2"))


def test_oidc_requires_preprovisioned_local_account() -> None:
    with pytest.raises(HTTPException) as exc:
        resolve_oidc_user(_claims(email="missing@example.com"))
    assert exc.value.status_code == 403
    assert "not provisioned" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_oidc_request_builds_access_context_from_local_user(monkeypatch: pytest.MonkeyPatch) -> None:
    local = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
        group_tags={"tenant-admin:tenant-a"},
    )

    async def verified(token: str, *, nonce=None):  # type: ignore[no-untyped-def]
        assert token == "good-id-token"
        assert nonce is None
        return _claims()

    monkeypatch.setattr("auth.oidc.verify_oidc_id_token", verified)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/whoami",
            "headers": [(b"authorization", b"Bearer good-id-token")],
        }
    )
    user = await get_current_user_oidc(request)
    assert user.uid == local.uid
    assert request.state.access.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_pkce_exchange_returns_only_verified_id_token_and_local_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-a",
    )

    async def discovery():  # type: ignore[no-untyped-def]
        return {
            "issuer": "https://id.example.com/realms/platform",
            "authorization_endpoint": "https://id.example.com/authorize",
            "token_endpoint": "https://id.example.com/token",
            "jwks_uri": "https://id.example.com/jwks",
        }

    async def verified(token: str, *, nonce=None):  # type: ignore[no-untyped-def]
        assert token == "provider-id-token"
        assert nonce == "n" * 16
        return _claims()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "id_token": "provider-id-token",
                "access_token": "must-not-be-returned",
                "refresh_token": "must-not-be-returned",
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, url: str, *, data: dict, headers: dict, auth=None):
            assert url == "https://id.example.com/token"
            assert data["code_verifier"] == "v" * 43
            assert headers["Accept"] == "application/json"
            assert auth is None
            return FakeResponse()

    monkeypatch.setattr("auth.oidc.get_oidc_discovery", discovery)
    monkeypatch.setattr("auth.oidc.verify_oidc_id_token", verified)
    monkeypatch.setattr("auth.oidc.httpx.AsyncClient", FakeClient)

    token, expires_in, user = await exchange_authorization_code(
        code="authorization-code",
        code_verifier="v" * 43,
        redirect_uri="http://localhost:3456/auth/oidc/callback",
        nonce="n" * 16,
    )
    assert token == "provider-id-token"
    assert expires_in > 0
    assert user.uid == local.uid
