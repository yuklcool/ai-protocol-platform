"""Phase 3 API tests for the first-class tenant admin lifecycle.

These tests deliberately assert the durable model (``tenants`` +
``tenant_domains``), not the historical ``clients/{domain}`` implementation.
The legacy wire shape remains covered: callers may still POST only ``domain``
and receive a stable tenant whose id temporarily equals that domain.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository

_PLATFORM_ADMIN = User(
    uid="platform-admin",
    email="owner@example.net",
    domain="example.net",
    group_tags=frozenset({"aitana-admin"}),
)
_ACME_ADMIN = User(
    uid="acme-admin",
    email="boss@acme.example",
    domain="acme.example",
    tenant_id="tenant-acme",
    group_tags=frozenset({"tenant-admin:tenant-acme"}),
)
_PLAIN_USER = User(
    uid="plain-user",
    email="user@acme.example",
    domain="acme.example",
    tenant_id="tenant-acme",
)


@pytest.fixture(autouse=True)
def _repository(monkeypatch):
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("ARTIFACT_BACKEND", "local")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    yield repo
    reset_repository_for_testing(None)


def _app(user: User) -> FastAPI:
    from admin.tenants import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return app


def _client(user: User) -> TestClient:
    return TestClient(_app(user))


def _allow_skill_validation():
    return patch("admin.tenants.skill_config.list_skills", return_value=[])


# ---------------------------------------------------------------------------
# Authority boundary
# ---------------------------------------------------------------------------


def test_plain_user_is_denied() -> None:
    response = _client(_PLAIN_USER).post(
        "/api/admin/tenants",
        json={"tenant_id": "tenant-acme", "domains": ["acme.example"]},
    )
    assert response.status_code == 403


def test_tenant_admin_cannot_manage_other_tenant() -> None:
    response = _client(_ACME_ADMIN).post(
        "/api/admin/tenants",
        json={"tenant_id": "tenant-other", "domains": ["other.example"]},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Backward compatibility + first-class identity
# ---------------------------------------------------------------------------


def test_legacy_domain_request_creates_first_class_tenant(_repository) -> None:
    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        response = _client(_PLATFORM_ADMIN).post(
            "/api/admin/tenants",
            json={"domain": "legacy.example", "display_name": "Legacy"},
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tenant_id"] == "legacy.example"
    assert body["domain"] == "legacy.example"
    assert body["config"]["tenantId"] == "legacy.example"
    assert body["config"]["domains"] == ["legacy.example"]

    tenant = _repository.get_document("tenants", "legacy.example")
    mapping = _repository.get_document("tenant_domains", "legacy.example")
    assert tenant is not None
    assert mapping == {"domain": "legacy.example", "tenantId": "legacy.example"}
    # New onboarding must not keep creating legacy client records.
    assert _repository.get_document("clients", "legacy.example") is None


def test_explicit_tenant_supports_multiple_domains(_repository) -> None:
    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        response = _client(_PLATFORM_ADMIN).post(
            "/api/admin/tenants",
            json={
                "tenant_id": "tenant-acme",
                "domains": ["acme.example", "acme.co.example", "ACME.EXAMPLE"],
                "display_name": "Acme",
                "model_policy": {"allowedProviders": ["openai-compatible"]},
                "storage_namespace": "org-acme",
                "quota": {"monthlyTokens": 1000000},
            },
        )

    assert response.status_code == 201, response.text
    config = response.json()["config"]
    assert config["tenantId"] == "tenant-acme"
    assert config["domains"] == ["acme.co.example", "acme.example"]
    assert config["storageNamespace"] == "org-acme"
    assert config["modelPolicy"]["allowedProviders"] == ["openai-compatible"]
    assert config["quota"]["monthlyTokens"] == 1000000
    for domain in config["domains"]:
        assert _repository.get_document("tenant_domains", domain)["tenantId"] == "tenant-acme"


def test_domainless_tenant_is_supported(_repository) -> None:
    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        response = _client(_PLATFORM_ADMIN).post(
            "/api/admin/tenants",
            json={"tenant_id": "oidc-customer-42", "domains": []},
        )

    assert response.status_code == 201, response.text
    config = response.json()["config"]
    assert config["tenantId"] == "oidc-customer-42"
    assert config["domains"] == []
    assert config["storageNamespace"] == "oidc-customer-42"


def test_missing_tenant_identity_is_rejected() -> None:
    with _allow_skill_validation():
        response = _client(_PLATFORM_ADMIN).post("/api/admin/tenants", json={})
    assert response.status_code == 422
    assert "tenant_id" in response.text


def test_unknown_skill_rejected_before_tenant_write(_repository) -> None:
    class _Skill:
        slug = "known-skill"

    with (
        patch("admin.tenants.skill_config.list_skills", return_value=[_Skill()]),
        patch("admin.tenants.record_admin_action"),
    ):
        response = _client(_PLATFORM_ADMIN).post(
            "/api/admin/tenants",
            json={
                "tenant_id": "tenant-bad-skill",
                "enabled_skills": ["known-skill", "missing-skill"],
            },
        )
    assert response.status_code == 422
    assert _repository.get_document("tenants", "tenant-bad-skill") is None


# ---------------------------------------------------------------------------
# Edit / domain remap / enable-disable lifecycle
# ---------------------------------------------------------------------------


def _seed_tenant(client: TestClient) -> None:
    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        response = client.post(
            "/api/admin/tenants",
            json={
                "tenant_id": "tenant-acme",
                "domains": ["old.acme.example"],
                "display_name": "Acme",
            },
        )
    assert response.status_code == 201, response.text


def test_edit_replaces_domain_mappings(_repository) -> None:
    client = _client(_PLATFORM_ADMIN)
    _seed_tenant(client)

    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        response = client.patch(
            "/api/admin/tenants/tenant-acme",
            json={"domains": ["new.acme.example", "second.acme.example"]},
        )

    assert response.status_code == 200, response.text
    assert _repository.get_document("tenant_domains", "old.acme.example") is None
    assert _repository.get_document("tenant_domains", "new.acme.example")["tenantId"] == "tenant-acme"
    assert _repository.get_document("tenant_domains", "second.acme.example")["tenantId"] == "tenant-acme"


def test_domain_mapping_collision_fails_closed(_repository) -> None:
    client = _client(_PLATFORM_ADMIN)
    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        first = client.post(
            "/api/admin/tenants",
            json={"tenant_id": "tenant-a", "domains": ["shared.example"]},
        )
        second = client.post(
            "/api/admin/tenants",
            json={"tenant_id": "tenant-b", "domains": ["shared.example"]},
        )
    assert first.status_code == 201
    assert second.status_code == 409
    assert _repository.get_document("tenant_domains", "shared.example")["tenantId"] == "tenant-a"
    assert _repository.get_document("tenants", "tenant-b") is None


def test_disable_and_enable_tenant(_repository) -> None:
    client = _client(_PLATFORM_ADMIN)
    _seed_tenant(client)

    with patch("admin.tenants.record_admin_action"):
        disabled = client.post("/api/admin/tenants/tenant-acme/disable")
        enabled = client.post("/api/admin/tenants/tenant-acme/enable")

    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True
    assert enabled.status_code == 200
    assert enabled.json()["disabled"] is False
    assert _repository.get_document("tenants", "tenant-acme")["disabled"] is False


def test_tenant_admin_can_edit_own_stable_tenant_only(_repository) -> None:
    platform = _client(_PLATFORM_ADMIN)
    _seed_tenant(platform)

    with _allow_skill_validation(), patch("admin.tenants.record_admin_action"):
        own = _client(_ACME_ADMIN).patch(
            "/api/admin/tenants/tenant-acme",
            json={"display_name": "Acme Updated"},
        )
        other = _client(_ACME_ADMIN).patch(
            "/api/admin/tenants/tenant-other",
            json={"display_name": "Nope"},
        )

    assert own.status_code == 200
    assert other.status_code == 403


# ---------------------------------------------------------------------------
# Self-host / provider-neutral validation
# ---------------------------------------------------------------------------


def test_local_storage_validation_never_constructs_gcs_client(_repository) -> None:
    with (
        _allow_skill_validation(),
        patch("admin.tenants.record_admin_action"),
        patch.dict("os.environ", {"ARTIFACT_BACKEND": "local", "OBJECT_STORAGE_BACKEND": "local"}),
    ):
        response = _client(_PLATFORM_ADMIN).post(
            "/api/admin/tenants",
            json={
                "tenant_id": "tenant-local",
                "domains": [],
                "storage_namespace": "local-tenant-files",
                "documents_bucket": "this-value-must-not-trigger-gcp",
            },
        )

    assert response.status_code == 201, response.text
    storage_check = next(
        item for item in response.json()["validation"]["checks"] if item["field"] == "storage_namespace"
    )
    assert storage_check["level"] == "ok"


def test_validate_reads_first_class_tenant() -> None:
    client = _client(_PLATFORM_ADMIN)
    _seed_tenant(client)
    with _allow_skill_validation():
        response = client.get("/api/admin/tenants/tenant-acme/validate")
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-acme"
    assert response.json()["ok"] is True
