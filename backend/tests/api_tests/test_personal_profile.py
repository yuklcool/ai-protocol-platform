"""Profile APIs bind ownership to verified identity, including protected admins."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User, get_current_user
from auth.local_jwt import create_local_user
from auth.routes import router as auth_router
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from tests.support.identity import identity_dependency


@pytest.fixture
def api(monkeypatch):
    from admin.accounts_routes import router as accounts_router

    monkeypatch.setenv("AUTH_BACKEND", "local-jwt")
    repo = MemoryRepository()
    reset_repository_for_testing(repo)
    create_local_user(
        email="admin@example.com", password="test-admin-password-1", uid="admin", group_tags=["aitana-admin"]
    )
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(accounts_router, prefix="/api/admin")
    actor = {"user": User(uid="admin", email="admin@example.com", group_tags=frozenset({"aitana-admin"}))}
    app.dependency_overrides[get_current_user] = identity_dependency(lambda: actor["user"])
    return TestClient(app), repo, actor


def test_admin_personal_configuration_is_editable_while_disable_is_protected(api):
    client, repo, _ = api
    repo.set_document("user_profiles", "admin", {"ragCorpusName": "preserved"})
    saved = client.put(
        "/api/admin/accounts/admin@example.com/profile", json={"skills": [], "information": "ADMIN-ONLY"}
    )
    assert saved.status_code == 200
    assert client.get("/api/auth/profile").json()["information"] == "ADMIN-ONLY"
    assert repo.get_document("user_profiles", "admin")["ragCorpusName"] == "preserved"
    assert client.patch("/api/admin/accounts/admin@example.com", json={"disabled": True}).status_code == 422


def test_self_service_cannot_select_another_owner_or_grant_tools(api):
    client, repo, actor = api
    repo.set_document("user_profiles", "admin", {"information": "SECRET"})
    actor["user"] = User(uid="member", email="member@example.com")
    assert client.get("/api/auth/profile?user_id=admin").json() == {"skills": [], "information": ""}
    assert client.put("/api/auth/profile", json={"information": "mine", "userId": "admin"}).status_code == 422
    assert client.put("/api/auth/profile", json={"tools": ["dangerous"]}).status_code == 422
    assert client.put("/api/auth/profile", json={"skills": [], "information": "MINE"}).status_code == 200
    assert repo.get_document("user_profiles", "admin")["information"] == "SECRET"
    assert repo.get_document("user_profiles", "member")["information"] == "MINE"
    assert client.get("/api/admin/accounts/admin@example.com/profile").status_code == 403


def test_two_accounts_cannot_share_the_same_personal_data_identity(api):
    with pytest.raises(ValueError, match="already belongs"):
        create_local_user(email="other@example.com", password="other-test-password", uid="admin")


def test_ambiguous_legacy_identity_is_denied_before_personal_access(api):
    from fastapi import HTTPException

    from auth.capability_access import refresh_authorization

    _client, repo, actor = api
    repo.set_document("auth_users", "legacy-duplicate", {"uid": "admin", "email": "other@example.com"})
    with pytest.raises(HTTPException) as denied:
        refresh_authorization(actor["user"].model_copy(update={"auth_mode": "local-jwt"}))
    assert denied.value.status_code == 403
