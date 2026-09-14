from __future__ import annotations

from auth import User
from object_storage.gcs import LegacyGcsObjectStorage
from tools.documents.routes import _storage_binding


def test_legacy_gcs_document_uses_compatibility_adapter() -> None:
    user = User(uid="user_a", email="alice@example.com", domain="example.com")
    doc = {
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
