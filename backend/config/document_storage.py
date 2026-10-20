"""Deployment-wide document bucket; private objects remain user-owned."""

import os


def resolve_documents_bucket(user=None) -> str:
    return os.environ.get("DOCUMENTS_BUCKET", "aitana-documents-bucket")


def resolve_channel_bucket() -> str:
    return os.environ.get("CHANNEL_DOCUMENTS_BUCKET") or resolve_documents_bucket()
