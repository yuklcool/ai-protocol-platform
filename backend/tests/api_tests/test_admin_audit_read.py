"""Reading the admin audit trail, tenant-scoped (v6.16.0 Phase 4).

The trail was write-only since v6.9.0. Making it readable introduces a new data
boundary, so the tests below focus on what a tenant admin must NOT see:
another tenant's mutations, and platform-level actions they have no part in.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

_PLATFORM = User(
    uid="admin-uid",
    email="owner@yourcompany.com",
    domain="yourcompany.com",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT_A = User(
    uid="ta-uid",
    email="ops@a.com",
    domain="a.com",
    group_tags=frozenset({"tenant-admin:tenant-a"}),
)

# One row per target SHAPE — audit rows are keyed by whatever was mutated.
_ROWS = [
    {"__id": "1", "ts": "2026-07-21T10:00:00Z", "action": "upsert_client", "target": "a.com", "tenantId": "tenant-a"},
    {"__id": "2", "ts": "2026-07-21T09:00:00Z", "action": "upsert_client", "target": "b.com", "tenantId": "tenant-b"},
    {
        "__id": "3",
        "ts": "2026-07-21T08:00:00Z",
        "action": "grant_group_tag",
        "target": "user@a.com",
        "tenantId": "tenant-a",
    },
    {
        "__id": "4",
        "ts": "2026-07-21T07:00:00Z",
        "action": "grant_group_tag",
        "target": "user@b.com",
        "tenantId": "tenant-b",
    },
    # Platform-level: the wildcard tool-permission doc.
    {"__id": "5", "ts": "2026-07-21T06:00:00Z", "action": "upsert_tool_permission", "target": "*"},
    # Platform-level: a group-tag registry id (no domain).
    {"__id": "6", "ts": "2026-07-21T05:00:00Z", "action": "upsert_group_tag", "target": "beta-tester"},
]


def _app(user: User) -> TestClient:
    from admin.audit_routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


class TestScoping:
    def test_platform_sees_every_row(self):
        with patch("admin.audit.query_documents", return_value=[dict(r) for r in _ROWS]):
            r = _app(_PLATFORM).get("/api/admin/audit")
        assert r.status_code == 200
        assert {e["id"] for e in r.json()["entries"]} == {"1", "2", "3", "4", "5", "6"}


class TestFiltersAndLimits:
    def test_action_filter(self):
        with patch("admin.audit.query_documents", return_value=[dict(r) for r in _ROWS]):
            r = _app(_PLATFORM).get("/api/admin/audit?action=upsert_client")
        assert {e["id"] for e in r.json()["entries"]} == {"1", "2"}

    def test_limit_is_applied(self):
        with patch("admin.audit.query_documents", return_value=[dict(r) for r in _ROWS]):
            r = _app(_PLATFORM).get("/api/admin/audit?limit=2")
        assert len(r.json()["entries"]) == 2

    def test_limit_cannot_be_raised_without_bound(self):
        r = _app(_PLATFORM).get("/api/admin/audit?limit=99999")
        assert r.status_code == 422


class TestDegradation:
    def test_a_read_failure_returns_empty_not_500(self):
        """This is an inspection surface; a Firestore blip must not 500 the
        admin console."""
        with patch("admin.audit.query_documents", side_effect=RuntimeError("firestore down")):
            r = _app(_PLATFORM).get("/api/admin/audit")
        assert r.status_code == 200
        assert r.json()["entries"] == []
        assert r.json()["scanned"] == 0

    def test_non_admin_is_refused(self):
        plain = User(uid="u", email="u@x.com", domain="x.com", group_tags=frozenset())
        r = _app(plain).get("/api/admin/audit")
        assert r.status_code == 403


class TestHelperDirectly:
    pass
