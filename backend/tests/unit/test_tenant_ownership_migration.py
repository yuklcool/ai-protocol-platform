"""Production-safety tests for legacy tenant ownership migration + rollback."""

from __future__ import annotations

import json

import pytest

from db.repositories.memory import MemoryRepository
from scripts.migrate_tenants import migrate
from scripts.tenant_migration_journal import OP_COLLECTION, RUN_COLLECTION, rollback_migration


def _seed_full_legacy_graph(repository: MemoryRepository) -> None:
    for domain in ("a.example", "alt-a.example"):
        repository.set_document(
            "clients",
            domain,
            {
                "display_name": "Tenant A",
                "enabled_skills": ["ops"],
                "default_skill": "ops",
            },
        )
        repository.set_document(
            "tool_permissions",
            domain,
            {"type": "domain", "tools": ["search", "status"], "denied": ["danger"]},
        )

    repository.set_document(
        "auth_users",
        "local-user-1",
        {
            "uid": "u1",
            "email": "alice@a.example",
            "domain": "a.example",
            "passwordHash": "scrypt$SECRET-MUST-NOT-BE-JOURNALED",
            "groupTags": ["reader", "tenant-admin:a.example"],
        },
    )
    repository.set_document(
        "tool_permissions",
        "alice@a.example",
        {"type": "user", "tools": ["search"], "denied": []},
    )
    repository.set_document(
        "admin_audit",
        "audit-client",
        {
            "tenantId": "",
            "actorTenantId": "",
            "actorEmail": "operator@unrelated.example",
            "action": "upsert_client",
            "target": "a.example",
        },
    )
    repository.set_document(
        "admin_audit",
        "audit-user",
        {
            "tenantId": "",
            "actorTenantId": "",
            "actorEmail": "someone@else.example",
            "action": "grant_group_tag",
            "target": "alice@a.example",
        },
    )
    repository.set_document(
        "admin_audit",
        "audit-ambiguous",
        {
            "tenantId": "",
            "actorTenantId": "",
            "actorEmail": "alice@a.example",
            "action": "unknown_legacy_action",
            "target": "opaque-resource",
        },
    )


def test_apply_migrates_only_trusted_ownership_and_journal_contains_no_password_hash() -> None:
    repository = MemoryRepository()
    _seed_full_legacy_graph(repository)

    result = migrate(
        repository,
        {"a.example": "tenant-a", "alt-a.example": "tenant-a"},
        apply=True,
        require_explicit=True,
    )

    assert result.run_id
    assert result.users_updated == 1
    assert result.tenant_permissions_created == 1
    assert result.user_permissions_updated == 1
    assert result.audits_updated == 2

    tenant = repository.get_document("tenants", "tenant-a")
    assert tenant is not None
    assert tenant["domains"] == ["a.example", "alt-a.example"]
    assert repository.get_document("tenant_domains", "a.example")["tenantId"] == "tenant-a"

    tenant_rule = repository.get_document("tool_permissions", "tenant:tenant-a")
    assert tenant_rule == {
        "type": "tenant",
        "tools": ["search", "status"],
        "denied": ["danger"],
        "tenantId": "tenant-a",
    }
    assert repository.get_document("tool_permissions", "alice@a.example")["tenantId"] == "tenant-a"

    user = repository.get_document("auth_users", "local-user-1")
    assert user["tenantId"] == "tenant-a"
    assert user["groupTags"] == ["reader", "tenant-admin:tenant-a"]
    assert user["passwordHash"] == "scrypt$SECRET-MUST-NOT-BE-JOURNALED"

    assert repository.get_document("admin_audit", "audit-client")["tenantId"] == "tenant-a"
    assert repository.get_document("admin_audit", "audit-user")["tenantId"] == "tenant-a"
    # Actor email is never used as target ownership evidence.
    assert repository.get_document("admin_audit", "audit-ambiguous")["tenantId"] == ""

    run = repository.get_document(RUN_COLLECTION, result.run_id)
    assert run["status"] == "applied"
    operations = repository.query_documents(OP_COLLECTION, filters=[("runId", "==", result.run_id)], limit=None)
    serialized = json.dumps(operations, sort_keys=True)
    assert "passwordHash" not in serialized
    assert "SECRET-MUST-NOT-BE-JOURNALED" not in serialized


def test_rollback_restores_only_touched_fields_and_removes_created_documents() -> None:
    repository = MemoryRepository()
    _seed_full_legacy_graph(repository)
    result = migrate(
        repository,
        {"a.example": "tenant-a", "alt-a.example": "tenant-a"},
        apply=True,
        require_explicit=True,
    )
    assert result.run_id

    summary = rollback_migration(repository, result.run_id)

    assert summary["deleted"] >= 4  # tenant, two domain mappings, tenant permission
    assert repository.get_document("tenants", "tenant-a") is None
    assert repository.get_document("tenant_domains", "a.example") is None
    assert repository.get_document("tool_permissions", "tenant:tenant-a") is None

    user = repository.get_document("auth_users", "local-user-1")
    assert "tenantId" not in user
    assert user["groupTags"] == ["reader", "tenant-admin:a.example"]
    assert user["passwordHash"] == "scrypt$SECRET-MUST-NOT-BE-JOURNALED"
    assert "tenantId" not in repository.get_document("tool_permissions", "alice@a.example")
    assert repository.get_document("admin_audit", "audit-client")["tenantId"] == ""
    assert repository.get_document(RUN_COLLECTION, result.run_id)["status"] == "rolled_back"


def test_rollback_refuses_drift_before_mutating_any_operation() -> None:
    repository = MemoryRepository()
    _seed_full_legacy_graph(repository)
    result = migrate(
        repository,
        {"a.example": "tenant-a", "alt-a.example": "tenant-a"},
        apply=True,
        require_explicit=True,
    )
    assert result.run_id

    repository.update_document("auth_users", "local-user-1", {"tenantId": "tenant-manual-change"})

    with pytest.raises(ValueError, match="rollback refused"):
        rollback_migration(repository, result.run_id)

    # Preflight happens before rollback mutations: created tenant resources are
    # still present when any one operation has drifted.
    assert repository.get_document("tenants", "tenant-a") is not None
    assert repository.get_document("tenant_domains", "a.example") is not None
    assert repository.get_document("tool_permissions", "tenant:tenant-a") is not None


def test_conflicting_domain_permissions_fail_before_any_migration_write() -> None:
    repository = MemoryRepository()
    repository.set_document("clients", "a.example", {"display_name": "Shared"})
    repository.set_document("clients", "b.example", {"display_name": "Shared"})
    repository.set_document("tool_permissions", "a.example", {"type": "domain", "tools": ["search"]})
    repository.set_document("tool_permissions", "b.example", {"type": "domain", "tools": ["billing"]})

    with pytest.raises(ValueError, match="tool permissions disagree"):
        migrate(
            repository,
            {"a.example": "tenant-shared", "b.example": "tenant-shared"},
            apply=True,
            require_explicit=True,
        )

    assert repository.get_document("tenants", "tenant-shared") is None
    assert repository.query_documents(RUN_COLLECTION, limit=None) == []


def test_existing_explicit_user_tenant_is_not_overwritten_from_email_domain() -> None:
    repository = MemoryRepository()
    repository.set_document("clients", "a.example", {"display_name": "A"})
    repository.set_document(
        "auth_users",
        "user-doc",
        {
            "uid": "u1",
            "email": "user@a.example",
            "domain": "a.example",
            "tenantId": "tenant-special",
            "passwordHash": "secret",
        },
    )
    repository.set_document(
        "tool_permissions",
        "user@a.example",
        {"type": "user", "tools": ["search"], "denied": []},
    )

    result = migrate(
        repository,
        {"a.example": "tenant-a"},
        apply=True,
        require_explicit=True,
    )

    assert repository.get_document("auth_users", "user-doc")["tenantId"] == "tenant-special"
    assert repository.get_document("tool_permissions", "user@a.example")["tenantId"] == "tenant-special"
    assert result.users_updated == 0
    assert result.user_permissions_updated == 1


def test_dry_run_creates_no_journal_or_ownership_records() -> None:
    repository = MemoryRepository()
    repository.set_document("clients", "a.example", {"display_name": "A"})

    result = migrate(
        repository,
        {"a.example": "tenant-a"},
        apply=False,
        require_explicit=True,
    )

    assert result.run_id is None
    assert repository.get_document("tenants", "tenant-a") is None
    assert repository.query_documents(RUN_COLLECTION, limit=None) == []
    assert repository.query_documents(OP_COLLECTION, limit=None) == []
