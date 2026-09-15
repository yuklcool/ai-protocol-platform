from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth import User
from object_storage.gcs import LegacyGcsObjectStorage
from tools.documents.routes import _storage_binding


def test_attributed_legacy_gcs_document_uses_compatibility_adapter() -> None:
    user = User(uid="user_a", email="alice@example.com", domain="example.com")
    doc = {
        "tenantId": "example.com",
        "userId": "user_a",
        "originalFilename": "old.pdf",
        "sourceFormat": "pdf",
        "sourceUrl": "gs://legacy-bucket/users/user_a/docs/f/old.pdf",
        "storagePath": "users/user_a/docs/f/old.pdf",
    }

    storage, tenant_id, key, backend = _storage_binding(doc, user)

    assert isinstance(storage, LegacyGcsObjectStorage)
    assert storage.bucket_name == "legacy-bucket"
    assert tenant_id == "example.com"
    assert key == "users/user_a/docs/f/old.pdf"
    assert backend == "gcs-legacy"


def test_unattributed_legacy_gcs_document_fails_closed() -> None:
    user = User(uid="user_a", email="alice@example.com", domain="example.com")
    legacy_doc = {
        "userId": "user_a",
        "originalFilename": "old.pdf",
        "sourceFormat": "pdf",
        "sourceUrl": "gs://legacy-bucket/users/user_a/docs/f/old.pdf",
        "storagePath": "users/user_a/docs/f/old.pdf",
    }

    with pytest.raises(HTTPException) as exc:
        _storage_binding(legacy_doc, user)

    assert exc.value.status_code == 403
