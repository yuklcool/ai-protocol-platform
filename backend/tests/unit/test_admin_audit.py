"""Tests for the append-only admin audit helper (admin/audit.py, v6.9.0 / 9.1)."""

from __future__ import annotations

import logging
from unittest.mock import patch

from admin import audit


def test_record_writes_an_append_only_document():
    with patch("admin.audit.set_document") as mock_set:
        audit.record_admin_action(
            actor_uid="admin1",
            actor_email="admin@x.com",
            action="grant_group_tag",
            target="user@y.com",
            before={"group_tags": []},
            after={"group_tags": ["ONE"]},
        )
    assert mock_set.call_count == 1
    coll, doc_id, data = mock_set.call_args[0]
    assert coll == "admin_audit"
    assert doc_id  # a generated uuid — append-only, never overwrites
    assert data["actorUid"] == "admin1"
    assert data["actorEmail"] == "admin@x.com"
    assert data["action"] == "grant_group_tag"
    assert data["target"] == "user@y.com"
    assert data["before"] == {"group_tags": []}
    assert data["after"] == {"group_tags": ["ONE"]}
    assert data["ts"]  # ISO timestamp present


def test_record_uses_a_fresh_id_each_call():
    with patch("admin.audit.set_document") as mock_set:
        audit.record_admin_action(actor_uid="a", action="x", target="t1")
        audit.record_admin_action(actor_uid="a", action="x", target="t2")
    id1 = mock_set.call_args_list[0][0][1]
    id2 = mock_set.call_args_list[1][0][1]
    assert id1 != id2


def test_record_never_raises_on_write_failure(caplog):
    caplog.set_level(logging.ERROR, logger="admin.audit")
    with patch("admin.audit.set_document", side_effect=RuntimeError("firestore down")):
        # Best-effort: must NOT raise into the caller (a mutation must not fail
        # because the audit store blipped) — but the loss is logged at ERROR.
        audit.record_admin_action(actor_uid="a", action="x", target="t")
    assert any("admin_audit write FAILED" in r.message for r in caplog.records)


def test_target_tenant_is_independent_of_actor_and_payload():
    with patch("admin.audit.set_document") as write:
        audit.record_admin_action(
            actor_uid="platform-admin", actor_tenant_id="operator-tenant",
            tenant_id="tenant-a", action="edit_tenant", target="shared@example.com",
            after={"tenantId": "tenant-b"},
        )
    data = write.call_args.args[2]
    assert data["tenantId"] == "tenant-a"
    assert data["actorTenantId"] == "operator-tenant"


def test_repository_filters_and_counts_exclude_unattributed_and_other_tenant():
    from db.repositories.memory import MemoryRepository

    repo = MemoryRepository()
    rows = [
        {"tenantId": "tenant-a", "target": "same@example.com"},
        {"tenantId": "tenant-b", "target": "same@example.com"},
        {"target": "tenant-a"},
        {"tenantId": "", "actorTenantId": "tenant-a", "target": "same@example.com"},
    ]
    for i, row in enumerate(rows):
        repo.set_document("admin_audit", str(i), dict(row, ts=str(i), action="edit"))
    with patch("admin.audit.query_documents", wraps=repo.query_documents) as query:
        own, count = audit.list_admin_actions(domains=frozenset({"tenant-a"}))
        assert count == 1
        assert [r["__id"] for r in own] == ["0"]
        assert query.call_args.kwargs["filters"] == [("tenantId", "in", ["tenant-a"])]
        platform, count = audit.list_admin_actions(domains=None)
        assert len(platform) == count == 4
