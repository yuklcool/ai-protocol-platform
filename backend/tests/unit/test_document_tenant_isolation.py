"""Phase 3 regressions for Document / Folder stable-tenant isolation.

The same uid is intentionally reused in multiple tenants.  User ownership alone
must never authorize a folder, document metadata row, or document binary scope
across a tenant boundary.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from auth.models import User
from db.folders import create_folder, list_folder_documents, list_folders
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from tools.documents.routes import _owned_document, _tenant_namespace


@pytest.fixture()
def repo():
    repository = MemoryRepository()
    reset_repository_for_testing(repository)
    yield repository
    reset_repository_for_testing(None)


def _user(tenant_id: str, *, domain: str = "legacy.example") -> User:
    return User(
        uid="same-uid",
        email="same@example.com",
        domain=domain,
        tenant_id=tenant_id,
    )


def test_folder_lists_partition_same_uid_by_tenant(repo: MemoryRepository) -> None:
    a = create_folder("same-uid", "Tenant A", tenant_id="tenant-a")
    b = create_folder("same-uid", "Tenant B", tenant_id="tenant-b")

    a_rows = list_folders("same-uid", tenant_id="tenant-a")
    b_rows = list_folders("same-uid", tenant_id="tenant-b")

    assert [row["id"] for row in a_rows] == [a["id"]]
    assert [row["id"] for row in b_rows] == [b["id"]]
    assert a_rows[0]["tenantId"] == "tenant-a"
    assert b_rows[0]["tenantId"] == "tenant-b"


def test_folder_document_query_filters_tenant_before_user(repo: MemoryRepository) -> None:
    repo.set_document(
        "parsed_documents",
        "doc-a",
        {
            "tenantId": "tenant-a",
            "userId": "same-uid",
            "folderId": "shared-folder-id",
            "createdAt": "2026-09-15T00:00:00+00:00",
        },
    )
    repo.set_document(
        "parsed_documents",
        "doc-b",
        {
            "tenantId": "tenant-b",
            "userId": "same-uid",
            "folderId": "shared-folder-id",
            "createdAt": "2026-09-15T00:00:01+00:00",
        },
    )

    a_rows = list_folder_documents("same-uid", "shared-folder-id", tenant_id="tenant-a")
    b_rows = list_folder_documents("same-uid", "shared-folder-id", tenant_id="tenant-b")

    assert [row["__id"] for row in a_rows] == ["doc-a"]
    assert [row["__id"] for row in b_rows] == ["doc-b"]


def test_document_owner_uid_does_not_override_tenant_boundary() -> None:
    user = _user("tenant-a")
    foreign_doc = {
        "tenantId": "tenant-b",
        "userId": "same-uid",
        "storageBackend": "local",
        "storagePath": "users/same-uid/docs/f/report.pdf",
    }
    with patch("tools.documents.routes._get_document_record", return_value=foreign_doc):
        with pytest.raises(HTTPException) as exc:
            _owned_document("doc-b", user)
    assert exc.value.status_code == 403


def test_document_without_tenant_id_fails_closed() -> None:
    user = _user("tenant-a")
    legacy_unattributed = {
        "userId": "same-uid",
        "storageBackend": "local",
        "storagePath": "users/same-uid/docs/f/report.pdf",
    }
    with patch("tools.documents.routes._get_document_record", return_value=legacy_unattributed):
        with pytest.raises(HTTPException) as exc:
            _owned_document("legacy-doc", user)
    assert exc.value.status_code == 403


def test_explicit_tenant_id_wins_over_legacy_domain_mapping() -> None:
    user = _user("tenant-a", domain="tenant-b.example")
    assert _tenant_namespace(user) == "tenant-a"


def test_legacy_identity_can_still_use_domain_mapping() -> None:
    user = _user("", domain="legacy.example")
    assert _tenant_namespace(user) == "legacy.example"


def test_identity_without_tenant_or_domain_is_rejected() -> None:
    user = _user("", domain="")
    with pytest.raises(HTTPException) as exc:
        _tenant_namespace(user)
    assert exc.value.status_code == 403
