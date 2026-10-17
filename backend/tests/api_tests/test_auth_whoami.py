"""Tests for GET /api/auth/whoami.

Mocks `firebase_admin.auth.verify_id_token` — no real JWTs are minted.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from auth.firebase_auth import get_current_user as firebase_get_current_user
from auth.routes import router as auth_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_current_user] = firebase_get_current_user
    return TestClient(app)


def test_whoami_no_auth_401(client: TestClient) -> None:
    resp = client.get("/api/auth/whoami")
    assert resp.status_code == 401


def test_whoami_valid_token_echoes_identity(client: TestClient) -> None:
    with patch("firebase_admin.auth.verify_id_token") as mock_verify:
        mock_verify.return_value = {
            "uid": "mark-uid",
            "email": "owner@yourcompany.com",
            "groupTags": ["aitana-admin", "ops"],
        }
        resp = client.get("/api/auth/whoami", headers={"Authorization": "Bearer good.jwt"})
    assert resp.status_code == 200
    assert resp.json() == {
        "uid": "mark-uid",
        "email": "owner@yourcompany.com",
        "domain": "yourcompany.com",
        "tenantId": "yourcompany.com",
        "authMode": "firebase",
        "groupTags": ["aitana-admin", "ops"],
    }


def test_whoami_missing_group_tags_returns_empty_list(client: TestClient) -> None:
    with patch("firebase_admin.auth.verify_id_token") as mock_verify:
        mock_verify.return_value = {"uid": "other-uid", "email": "other@example.com"}
        resp = client.get("/api/auth/whoami", headers={"Authorization": "Bearer good.jwt"})
    assert resp.status_code == 200
    assert resp.json() == {
        "uid": "other-uid",
        "email": "other@example.com",
        "domain": "example.com",
        "tenantId": "example.com",
        "authMode": "firebase",
        "groupTags": [],
    }
