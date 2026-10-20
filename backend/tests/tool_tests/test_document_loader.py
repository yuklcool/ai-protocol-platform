"""附件校验针对真实持久化记录,不依赖 Artifact 缓存。"""

import pytest

from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from tools.documents.access import DocumentUnavailable, readable_document, validate_selection


@pytest.fixture()
def repo():
    store = MemoryRepository()
    reset_repository_for_testing(store)
    store.set_document(
        "parsed_documents",
        "a",
        {
            "tenantId": "t1",
            "userId": "same",
            "parseStatus": "parsed",
            "originalFilename": "notes.txt",
            "blocks": [{"type": "paragraph", "text": "AIP-119"}],
        },
    )
    yield store
    reset_repository_for_testing(None)


def test_selection_checks_user_owner(repo):
    assert validate_selection(["a", "a"], user_id="same") == ["a"]
    for user in ("other", ""):
        with pytest.raises(DocumentUnavailable):
            readable_document("a", user_id=user)


@pytest.mark.parametrize("status", ["pending", "pending_ai_extraction", "failed"])
def test_unreadable_file_blocks_analysis_instead_of_false_success(repo, status):
    repo.set_document("parsed_documents", "a", {"parseStatus": status, "parseError": "解析未完成"}, merge=True)
    with pytest.raises(DocumentUnavailable, match="解析未完成"):
        validate_selection(["a"], user_id="same")
    assert readable_document("a", user_id="same", ready=False)


def test_missing_deleted_empty_and_excessive_selection_are_rejected(repo):
    with pytest.raises(DocumentUnavailable):
        validate_selection(["a"] * 11, user_id="same")
    with pytest.raises(DocumentUnavailable):
        validate_selection(["missing"], user_id="same")
    repo.set_document("parsed_documents", "a", {"blocks": []}, merge=True)
    with pytest.raises(DocumentUnavailable):
        validate_selection(["a"], user_id="same")
    repo.set_document("parsed_documents", "a", {"deletionStatus": "deleting"}, merge=True)
    with pytest.raises(DocumentUnavailable):
        readable_document("a", user_id="same", ready=False)
