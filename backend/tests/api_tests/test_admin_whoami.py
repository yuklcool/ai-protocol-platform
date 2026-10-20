"""API tests for GET /api/admin/whoami — the admin role probe (v6.16.0 M1).

The point of this endpoint is that the frontend can distinguish three states
without interpreting an error code: platform admin, tenant admin, and not an
admin. Before it existed, the UI probed `GET /api/admin/clients` (a *data*
endpoint) and read 403 as "not an admin" — which is exactly why a
`tenant-admin` holder never saw the Admin link.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user

_PLATFORM = User(
    uid="admin-uid",
    email="owner@yourcompany.com",
    domain="yourcompany.com",
    group_tags=frozenset({"aitana-admin"}),
)
_TENANT = User(
    uid="tenant-uid",
    email="ops@acmeenergy.com",
    domain="acmeenergy.com",
    group_tags=frozenset({"tenant-admin:acmeenergy.com"}),
)
_MULTI = User(
    uid="multi-uid",
    email="ops@group.com",
    domain="group.com",
    group_tags=frozenset({"tenant-admin:b.com", "tenant-admin:a.com"}),
)
_PLAIN = User(
    uid="user-uid",
    email="user@example.com",
    domain="example.com",
    group_tags=frozenset({"ONE"}),
)


def _client(user: User) -> TestClient:
    from admin.routes import router

    app = FastAPI()
    app.include_router(router)

    async def _override(request: Request) -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


class TestWhoAmI:
    def test_platform_admin(self):
        r = _client(_PLATFORM).get("/api/admin/whoami")
        assert r.status_code == 200
        assert r.json()["scope"] == "platform"

    def test_non_admin_gets_200_none_not_403(self):
        """The never-silent contract: 'not an admin' is a *state*, not an error.

        A 403 here would be indistinguishable from a broken backend, and the UI
        would have to guess — which is the bug this endpoint replaces.
        """
        r = _client(_PLAIN).get("/api/admin/whoami")
        assert r.status_code == 200
        assert r.json()["scope"] == "none"
