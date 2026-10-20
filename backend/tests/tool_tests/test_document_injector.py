"""本轮附件直接进入模型输入;不存在用户级缓存、旧轮次或跨租户回退。"""

from types import SimpleNamespace

import pytest
from google.genai.types import Content, FunctionResponse, Part

from adk.callbacks import make_document_injector
from auth.models import User
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from observability.tenant_context import set_tenant_context
from tools.documents.access import DocumentUnavailable, read_attached_document

USER = User(uid="same", email="u@local.test", tenant_id="tenant-a")


@pytest.fixture()
def repo():
    store = MemoryRepository()
    reset_repository_for_testing(store)
    for ref in ("a", "b"):
        store.set_document(
            "parsed_documents",
            ref,
            {
                "tenantId": "tenant-a",
                "userId": "same",
                "originalFilename": f"{ref}.txt",
                "parseStatus": "parsed",
                "blocks": [{"type": "paragraph", "text": f"UNIQUE-{ref}", "source": "第 1 行"}],
            },
        )
    yield store
    reset_repository_for_testing(None)


def request():
    return SimpleNamespace(contents=[Content(role="user", parts=[Part.from_text(text="分析所选文件")])])


def texts(req):
    return "\n".join(part.text or "" for content in req.contents for part in (content.parts or []))


@pytest.mark.asyncio
async def test_current_selection_and_source_locations_reach_the_model(repo):
    callback = make_document_injector(USER)
    req = request()
    await callback(SimpleNamespace(state={"document_ids": ["a", "b"]}), req)
    assert "UNIQUE-a" in texts(req) and "UNIQUE-b" in texts(req)
    assert "a.txt" in texts(req) and "第 1 行" in texts(req)
    assert len(req.contents) == 3
    await callback(SimpleNamespace(state={"document_ids": ["a", "b"]}), req)
    assert len(req.contents) == 3


@pytest.mark.asyncio
async def test_empty_selection_ignores_loaded_flags_and_other_session_state(repo):
    req = request()
    await make_document_injector(USER)(
        SimpleNamespace(
            state={
                "document_ids": [],
                "user:docs_loaded": ["a", "b"],
                "app:docs_loaded": ["a"],
            }
        ),
        req,
    )
    assert len(req.contents) == 1
    assert "UNIQUE" not in texts(req)


@pytest.mark.asyncio
async def test_reparse_or_edits_do_not_reuse_stale_artifacts(repo):
    callback = make_document_injector(USER)
    context = SimpleNamespace(state={"document_ids": ["a"]})
    first = request()
    await callback(context, first)
    repo.set_document("parsed_documents", "a", {"blocks": [{"type": "paragraph", "text": "UPDATED"}]}, merge=True)
    second = request()
    await callback(context, second)
    assert "UPDATED" in texts(second) and "UNIQUE-a" not in texts(second)


@pytest.mark.asyncio
async def test_same_uid_other_tenant_cannot_read_content(repo):
    other = USER.model_copy(update={"tenant_id": "tenant-b"})
    with pytest.raises(DocumentUnavailable):
        await make_document_injector(other)(SimpleNamespace(state={"document_ids": ["a"]}), request())


@pytest.mark.asyncio
async def test_missing_or_failed_attachment_stops_before_model_call(repo):
    repo.set_document("parsed_documents", "a", {"parseStatus": "failed"}, merge=True)
    with pytest.raises(DocumentUnavailable):
        await make_document_injector(USER)(SimpleNamespace(state={"document_ids": ["a"]}), request())


@pytest.mark.asyncio
async def test_tool_roundtrip_does_not_duplicate_document_input(repo):
    req = request()
    req.contents[-1].parts = [
        Part(function_response=FunctionResponse(name="read_attached_document", response={"ok": True}))
    ]
    await make_document_injector(USER)(SimpleNamespace(state={"document_ids": ["a"]}), req)
    assert len(req.contents) == 1


@pytest.mark.asyncio
async def test_long_content_declares_scope_and_is_readable_by_offset(repo):
    content = "A" * 80000 + "UNIQUE-END-119"
    repo.set_document("parsed_documents", "a", {"blocks": [{"type": "paragraph", "text": content}]}, merge=True)
    req = request()
    context = SimpleNamespace(state={"document_ids": ["a"]})
    await make_document_injector(USER)(context, req)
    assert "当前仅提供前" in texts(req) and "UNIQUE-END-119" not in texts(req)
    assert len(texts(req)) < 33000
    set_tenant_context(USER)
    result = read_attached_document("a", offset=78000, tool_context=context)
    assert "UNIQUE-END-119" in result["text"] and result["hasMore"] is False
    with pytest.raises(DocumentUnavailable):
        read_attached_document("b", tool_context=context)
