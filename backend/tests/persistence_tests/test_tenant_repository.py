from __future__ import annotations

import pytest

from db.repositories.memory import MemoryRepository
from db.tenant_repository import TenantIsolationError, TenantRepository


def test_scoped_write_injects_tenant_and_read_succeeds():
    base = MemoryRepository()
    repo = TenantRepository(base, "tenant-a")

    repo.set_document("things", "1", {"name": "alpha"})

    assert base.get_document("things", "1")["tenantId"] == "tenant-a"
    assert repo.get_document("things", "1")["name"] == "alpha"


def test_cross_tenant_get_fails_closed():
    base = MemoryRepository()
    base.set_document("things", "1", {"tenantId": "tenant-b", "name": "secret"})
    repo = TenantRepository(base, "tenant-a")

    with pytest.raises(TenantIsolationError):
        repo.get_document("things", "1")


def test_unscoped_legacy_document_is_not_visible():
    base = MemoryRepository()
    base.set_document("things", "1", {"name": "legacy"})
    repo = TenantRepository(base, "tenant-a")

    with pytest.raises(TenantIsolationError):
        repo.get_document("things", "1")


def test_query_always_adds_tenant_filter():
    base = MemoryRepository()
    base.set_document("things", "a", {"tenantId": "tenant-a", "kind": "x"})
    base.set_document("things", "b", {"tenantId": "tenant-b", "kind": "x"})
    repo = TenantRepository(base, "tenant-a")

    rows = repo.query_documents("things", filters=[("kind", "==", "x")])

    assert [row["__id"] for row in rows] == ["a"]


def test_query_cannot_override_tenant_scope():
    repo = TenantRepository(MemoryRepository(), "tenant-a")

    with pytest.raises(TenantIsolationError):
        repo.query_documents("things", filters=[("tenantId", "==", "tenant-b")])


def test_explicit_conflicting_write_is_rejected():
    repo = TenantRepository(MemoryRepository(), "tenant-a")

    with pytest.raises(TenantIsolationError):
        repo.set_document("things", "1", {"tenantId": "tenant-b"})


def test_update_delete_and_atomic_mutations_cannot_cross_tenant():
    base = MemoryRepository()
    base.set_document("things", "1", {"tenantId": "tenant-b", "count": 0, "tags": []})
    repo = TenantRepository(base, "tenant-a")

    operations = [
        lambda: repo.update_document("things", "1", {"name": "oops"}),
        lambda: repo.delete_document("things", "1"),
        lambda: repo.increment_field("things", "1", "count"),
        lambda: repo.array_union_field("things", "1", "tags", ["x"]),
    ]
    for operation in operations:
        with pytest.raises(TenantIsolationError):
            operation()
