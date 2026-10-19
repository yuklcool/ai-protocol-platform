from __future__ import annotations

from unittest.mock import patch

import pytest

from auth import User
from observability.tenant_context import _tenant_context, set_tenant_context
from tools.documents.context import build_document_context


@pytest.fixture(autouse=True)
def document_identity():
    token = _tenant_context.set(None)
    set_tenant_context(
        User(uid="context-user", email="user@example.com", domain="example.com", tenant_id="context-tenant")
    )
    yield
    _tenant_context.reset(token)


def test_build_document_context_reads_repository_facade() -> None:
    doc = {
        "userId": "context-user",
        "tenantId": "context-tenant",
        "originalFilename": "report.txt",
        "parseStatus": "parsed",
        "blocks": [{"type": "paragraph", "text": "Repository backed content"}],
        "editedBlocks": {},
    }
    with patch("tools.documents.access.get_document", return_value=doc) as get_doc:
        content, blocks = build_document_context("doc-1")

    get_doc.assert_called_once_with("parsed_documents", "doc-1")
    assert "Repository backed content" in content
    assert blocks is None
