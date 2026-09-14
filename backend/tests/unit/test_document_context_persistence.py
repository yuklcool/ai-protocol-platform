from __future__ import annotations

from unittest.mock import patch

from tools.documents.context import build_document_context, list_documents_for_user


def test_build_document_context_reads_repository_facade() -> None:
    doc = {
        "originalFilename": "report.txt",
        "parseStatus": "parsed",
        "blocks": [{"type": "paragraph", "text": "Repository backed content"}],
        "editedBlocks": {},
    }
    with patch("tools.documents.context.get_document", return_value=doc) as get_doc:
        content, blocks = build_document_context("doc-1")

    get_doc.assert_called_once_with("parsed_documents", "doc-1")
    assert "Repository backed content" in content
    assert blocks is None


def test_list_documents_for_user_queries_canonical_collection() -> None:
    with patch("tools.documents.context.query_documents", return_value=[]) as query:
        result = list_documents_for_user("user-a", skill_id="skill-a", limit=7)

    assert result == []
    kwargs = query.call_args.kwargs
    assert kwargs["collection"] == "parsed_documents"
    assert ("userId", "==", "user-a") in kwargs["filters"]
    assert ("skillId", "==", "skill-a") in kwargs["filters"]
    assert kwargs["limit"] == 7
