"""Migration tests for clients/{domain} -> first-class tenants."""

from __future__ import annotations

import pytest

from db.repositories.memory import MemoryRepository
from db.tenants import TenantDirectory
from scripts.migrate_tenants import build_migration_plan, migrate, parse_mapping


def test_parse_mapping_allows_multiple_domains_to_one_tenant() -> None:
    mapping = parse_mapping([
        "ACME.COM=tenant-acme",
        "acme-energy.example=tenant-acme",
    ])
    assert mapping == {
        "acme.com": "tenant-acme",
        "acme-energy.example": "tenant-acme",
    }


def test_plan_defaults_to_domain_for_zero_breaking_change() -> None:
    plan = build_migration_plan(
        [{"__id": "legacy.example", "display_name": "Legacy"}],
    )
    assert list(plan) == ["legacy.example"]
    assert plan["legacy.example"].config().domains == ["legacy.example"]


def test_plan_merges_domains_only_when_policy_matches() -> None:
    rows = [
        {
            "__id": "acme.com",
            "display_name": "Acme",
            "enabled_skills": ["ops"],
            "default_skill": "ops",
        },
        {
            "__id": "acme-energy.example",
            "display_name": "Acme",
            "enabled_skills": ["ops"],
            "default_skill": "ops",
        },
    ]
    plan = build_migration_plan(
        rows,
        {
            "acme.com": "tenant-acme",
            "acme-energy.example": "tenant-acme",
        },
    )
    config = plan["tenant-acme"].config()
    assert config.domains == ["acme-energy.example", "acme.com"]
    assert config.enabled_skills == ["ops"]


def test_plan_fails_fast_if_merged_domains_have_conflicting_policy() -> None:
    rows = [
        {"__id": "a.example", "default_skill": "skill-a"},
        {"__id": "b.example", "default_skill": "skill-b"},
    ]
    with pytest.raises(ValueError, match="disagree on default_skill"):
        build_migration_plan(
            rows,
            {"a.example": "tenant-shared", "b.example": "tenant-shared"},
        )


def test_apply_writes_directory_and_backfills_local_auth_users() -> None:
    repository = MemoryRepository()
    repository.set_document(
        "clients",
        "acme.com",
        {
            "display_name": "Acme",
            "enabled_skills": ["ops"],
        },
    )
    repository.set_document(
        "auth_users",
        "user-doc",
        {
            "uid": "u1",
            "email": "alice@acme.com",
            "domain": "acme.com",
        },
    )

    configs, updated = migrate(
        repository,
        {"acme.com": "tenant-acme"},
        apply=True,
        require_explicit=True,
    )

    assert [c.tenant_id for c in configs] == ["tenant-acme"]
    assert updated == 1
    assert repository.get_document("auth_users", "user-doc")["tenantId"] == "tenant-acme"
    directory = TenantDirectory(repository)
    assert directory.tenant_id_for_domain("acme.com") == "tenant-acme"
    assert directory.get("tenant-acme").enabled_skills == ["ops"]


def test_dry_run_never_writes() -> None:
    repository = MemoryRepository()
    repository.set_document("clients", "legacy.example", {"display_name": "Legacy"})

    configs, updated = migrate(repository, {}, apply=False, require_explicit=False)

    assert [c.tenant_id for c in configs] == ["legacy.example"]
    assert updated == 0
    assert repository.get_document("tenants", "legacy.example") is None
    assert repository.get_document("tenant_domains", "legacy.example") is None
