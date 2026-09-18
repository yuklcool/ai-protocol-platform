from __future__ import annotations

import jwt
import pytest

from auth.firebase_auth import User
from auth.identity import auth_backend
from auth.local_jwt import (
    authenticate_credentials,
    create_local_user,
    hash_password,
    issue_access_token,
    user_from_token,
    verify_password,
)
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository


@pytest.fixture(autouse=True)
def isolated_repository(monkeypatch: pytest.MonkeyPatch):
    reset_repository_for_testing(MemoryRepository())
    monkeypatch.setenv("JWT_SIGNING_KEY", "test-signing-key-that-is-longer-than-32-bytes")
    monkeypatch.setenv("JWT_ISSUER", "test-issuer")
    monkeypatch.setenv("JWT_AUDIENCE", "test-audience")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
    yield
    reset_repository_for_testing(None)


def test_password_hash_is_scrypt_and_never_plaintext() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("scrypt$")
    assert "correct horse battery staple" not in encoded
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password value", encoded)


def test_create_and_authenticate_local_user() -> None:
    user = create_local_user(
        email="Admin@Example.COM",
        password="correct horse battery staple",
        group_tags={"aitana-admin", "tenant-admin:example.com"},
    )
    assert user.email == "admin@example.com"
    assert user.domain == "example.com"
    assert user.auth_mode == "local-jwt"
    assert "aitana-admin" in user.group_tags

    authenticated = authenticate_credentials("admin@example.com", "correct horse battery staple")
    assert authenticated == user
    assert authenticate_credentials("admin@example.com", "totally wrong password") is None


def test_token_uses_database_as_authority_for_roles() -> None:
    original = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        group_tags={"aitana-admin"},
    )
    token, expires_in = issue_access_token(original)
    assert expires_in == 3600

    # Re-seed the same account with changed roles while preserving its UID.
    updated = create_local_user(
        email="admin@example.com",
        password="another strong password",
        group_tags={"tenant-admin:example.com"},
        overwrite=True,
    )
    assert updated.uid == original.uid

    resolved = user_from_token(token)
    assert resolved.uid == original.uid
    assert resolved.group_tags == frozenset({"tenant-admin:example.com"})
    assert "aitana-admin" not in resolved.group_tags


def test_previous_signing_key_supports_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    user = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        group_tags={"aitana-admin"},
    )
    token, _ = issue_access_token(user)

    old_key = "test-signing-key-that-is-longer-than-32-bytes"
    monkeypatch.setenv("JWT_SIGNING_KEY", "new-signing-key-that-is-also-longer-than-32-bytes")
    monkeypatch.setenv("JWT_PREVIOUS_SIGNING_KEYS", old_key)
    assert user_from_token(token).uid == user.uid


def test_invalid_signature_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    user = create_local_user(
        email="admin@example.com",
        password="correct horse battery staple",
        group_tags={"aitana-admin"},
    )
    token, _ = issue_access_token(user)
    monkeypatch.setenv("JWT_SIGNING_KEY", "different-key-that-is-longer-than-thirty-two-bytes")
    monkeypatch.delenv("JWT_PREVIOUS_SIGNING_KEYS", raising=False)
    with pytest.raises(jwt.InvalidTokenError):
        user_from_token(token)


def test_auth_backend_defaults_and_stub_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_MODE", "1")
    monkeypatch.delenv("AUTH_BACKEND", raising=False)
    assert auth_backend() == "stub"

    monkeypatch.setenv("AUTH_BACKEND", "local-jwt")
    assert auth_backend() == "local-jwt"

    monkeypatch.setenv("LOCAL_MODE", "0")
    monkeypatch.setenv("AUTH_BACKEND", "stub")
    with pytest.raises(RuntimeError, match="only allowed"):
        auth_backend()


def test_user_model_remains_shared_contract() -> None:
    user = create_local_user(
        email="person@example.com",
        password="correct horse battery staple",
    )
    assert isinstance(user, User)


def test_oidc_mapping_keeps_local_tenant_and_roles_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    from auth.oidc import clear_oidc_cache, resolve_oidc_user

    monkeypatch.setenv("OIDC_ISSUER", "https://id.example.com/realms/platform")
    monkeypatch.setenv("OIDC_CLIENT_ID", "ai-protocol-platform")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://localhost:3456/auth/oidc/callback")
    monkeypatch.setenv("OIDC_SCOPES", "openid profile email")
    clear_oidc_cache()

    local = create_local_user(
        email="sso-admin@example.com",
        password="correct horse battery staple",
        tenant_id="tenant-authoritative",
        group_tags={"tenant-admin:tenant-authoritative"},
    )
    user = resolve_oidc_user(
        {
            "sub": "external-subject-1",
            "email": "sso-admin@example.com",
            "email_verified": True,
            "tenant_id": "attacker-tenant",
            "groupTags": ["aitana-admin"],
        }
    )

    assert user.uid == local.uid
    assert user.tenant_id == "tenant-authoritative"
    assert user.group_tags == frozenset({"tenant-admin:tenant-authoritative"})
    assert "aitana-admin" not in user.group_tags
    assert user.auth_mode == "oidc"
    clear_oidc_cache()


def test_oidc_bootstrap_creates_passwordless_platform_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    from auth.local_jwt import get_local_user_by_email
    from scripts.seed_selfhost_admin import main

    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://id.example.com/realms/platform")
    monkeypatch.setenv("OIDC_CLIENT_ID", "ai-protocol-platform")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://localhost:3456/auth/oidc/callback")
    monkeypatch.setenv("OIDC_SCOPES", "openid profile email")
    monkeypatch.setenv("SELFHOST_ADMIN_EMAIL", "external@example.com")
    monkeypatch.delenv("SELFHOST_ADMIN_PASSWORD", raising=False)

    assert main() == 0
    record = get_local_user_by_email("external@example.com")

    assert record is not None
    assert "passwordHash" not in record
    assert "aitana-admin" in set(record.get("groupTags") or [])
    assert authenticate_credentials("external@example.com", "correct horse battery staple") is None
