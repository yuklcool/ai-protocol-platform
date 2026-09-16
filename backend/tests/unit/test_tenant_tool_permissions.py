"""Stable-tenant tool permission lookup tests.

These tests cover the migration bridge introduced for first-class tenant
ownership. Request code does not pass tenant ids into ``can_use_tool``; the
runtime normally recovers them from the trusted task-local auth context. The
explicit argument below keeps the unit cases deterministic.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from auth.permissions import COLLECTION, can_use_tool, clear_cache, tenant_permission_key


@pytest.fixture(autouse=True)
def _cache() -> None:
    clear_cache()
    yield
    clear_cache()


def _docs(values: dict[str, dict | None]):
    def _get(collection: str, doc_id: str):
        assert collection == COLLECTION
        return values.get(doc_id)

    return patch("auth.permissions.fs.get_document", side_effect=_get)


def test_tenant_rule_precedes_legacy_domain_rule() -> None:
    docs = {
        "tenant:tenant-a": {"type": "tenant", "tenantId": "tenant-a", "tools": ["search"], "denied": []},
        "a.example": {"type": "domain", "tools": [], "denied": ["search"]},
    }
    with _docs(docs):
        assert can_use_tool("user@a.example", "a.example", "search", tenant_id="tenant-a") is True


def test_legacy_domain_rule_remains_fallback_during_migration() -> None:
    docs = {
        "a.example": {"type": "domain", "tools": ["search"], "denied": []},
    }
    with _docs(docs):
        assert can_use_tool("user@a.example", "a.example", "search", tenant_id="tenant-a") is True


def test_other_tenant_rule_is_never_considered() -> None:
    docs = {
        "tenant:tenant-b": {"type": "tenant", "tenantId": "tenant-b", "tools": ["secret_tool"], "denied": []},
    }
    with _docs(docs) as get_doc:
        assert can_use_tool("user@a.example", "a.example", "secret_tool", tenant_id="tenant-a") is False
    requested = [call.args[1] for call in get_doc.call_args_list]
    assert "tenant:tenant-b" not in requested


def test_same_email_cache_is_partitioned_by_tenant() -> None:
    docs = {
        "tenant:tenant-a": {"type": "tenant", "tools": ["search"], "denied": []},
        "tenant:tenant-b": {"type": "tenant", "tools": [], "denied": ["search"]},
    }
    with _docs(docs):
        assert can_use_tool("shared@example.com", "example.com", "search", tenant_id="tenant-a") is True
        assert can_use_tool("shared@example.com", "example.com", "search", tenant_id="tenant-b") is False


def test_user_specific_rule_still_has_highest_precedence() -> None:
    docs = {
        "user@a.example": {"type": "user", "tools": [], "denied": ["search"]},
        "tenant:tenant-a": {"type": "tenant", "tools": ["search"], "denied": []},
    }
    with _docs(docs):
        assert can_use_tool("user@a.example", "a.example", "search", tenant_id="tenant-a") is False


def test_tenant_permission_key_rejects_empty_by_returning_no_key() -> None:
    assert tenant_permission_key("") == ""
    assert tenant_permission_key(" tenant-a ") == "tenant:tenant-a"
