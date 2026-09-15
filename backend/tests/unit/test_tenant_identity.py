"""Tenant identity migration contract for Phase 3 / issue #9."""

from __future__ import annotations

import jwt
import pytest

from auth.access_context import build_access_context
from auth.local_jwt import _record_to_user, issue_access_token
from auth.models import User
from db.repositories.memory import MemoryRepository
from db.tenant_repository import TenantIsolationError, TenantRepository


def test_access_context_prefers_explicit_tenant_id_over_email_domain() -> None:
    user = User(
        uid="u1",
        email="alice@alpha.example",
        domain="alpha.example",
        tenant_id="tenant-acme",
        group_tags=frozenset({"tenant-admin:tenant-acme"}),
        auth_mode="local-jwt",
    )

    ctx = build_access_context(user)

    assert ctx.domain == "alpha.example"
    assert ctx.tenant_id == "tenant-acme"
    assert ctx.is_tenant_admin()
    assert not ctx.is_tenant_admin("tenant-other")


def test_access_context_keeps_legacy_domain_as_tenant_fallback() -> None:
    user = User(uid="legacy", email="user@legacy.example", domain="legacy.example")

    ctx = build_access_context(user)

    assert ctx.tenant_id == "legacy.example"


def test_local_jwt_record_uses_explicit_tenant_and_legacy_fallback() -> None:
    explicit = _record_to_user(
        {
            "uid": "u-explicit",
            "email": "alice@one.example",
            "domain": "one.example",
            "tenantId": "tenant-one",
            "groupTags": [],
        }
    )
    legacy = _record_to_user(
        {
            "uid": "u-legacy",
            "email": "bob@legacy.example",
            "domain": "legacy.example",
            "groupTags": [],
        }
    )

    assert explicit.tenant_id == "tenant-one"
    assert legacy.tenant_id == "legacy.example"


def test_local_jwt_carries_tenant_claim_without_making_it_authoritative(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SIGNING_KEY", "x" * 48)
    monkeypatch.setenv("JWT_ISSUER", "tenant-test")
    monkeypatch.setenv("JWT_AUDIENCE", "tenant-test")
    user = User(
        uid="u1",
        email="user@example.com",
        domain="example.com",
        tenant_id="tenant-stable",
        auth_mode="local-jwt",
    )

    token, _ = issue_access_token(user)
    decoded = jwt.decode(
        token,
        "x" * 48,
        algorithms=["HS256"],
        issuer="tenant-test",
        audience="tenant-test",
    )

    assert decoded["tenant_id"] == "tenant-stable"


def test_tenant_repository_is_fail_closed_and_rejects_cross_tenant_access() -> None:
    base = MemoryRepository()
    tenant_a = TenantRepository(base, "tenant-a")
    tenant_b = TenantRepository(base, "tenant-b")

    tenant_a.set_document("sessions", "s1", {"title": "A"})
    base.set_document("sessions", "legacy", {"title": "no tenant"})

    assert tenant_a.get_document("sessions", "s1")["tenantId"] == "tenant-a"
    assert tenant_a.query_documents("sessions") == [
        {"title": "A", "tenantId": "tenant-a", "__id": "s1"}
    ]

    with pytest.raises(TenantIsolationError):
        tenant_b.get_document("sessions", "s1")
    with pytest.raises(TenantIsolationError):
        tenant_a.get_document("sessions", "legacy")
    with pytest.raises(TenantIsolationError):
        tenant_a.set_document("sessions", "bad", {"tenantId": "tenant-b"})
