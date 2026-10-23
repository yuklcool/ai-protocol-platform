from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from db.firestore_inmemory import InMemoryFirestoreClient
from db.persistence import reset_repository_for_testing
from db.repositories.firestore import FirestoreRepository
from db.repositories.memory import MemoryRepository
from db.task_status import task_projection
from protocols.action_claims import claim_action
from tests.support.session_search import client, document
from tools.task_plan import update_task_plan


@pytest.fixture(params=[MemoryRepository, FirestoreRepository])
def repo(request):
    value = request.param(client=InMemoryFirestoreClient())
    reset_repository_for_testing(value)
    return value


@pytest.fixture
def api(repo):
    yield from client()


def test_atomic_create_keeps_one_winner(repo):
    with ThreadPoolExecutor(max_workers=8) as executor:
        winners = list(executor.map(lambda n: repo.create_document("claims", "same", {"value": n}), range(32)))
    assert sum(winners) == 1
    assert repo.get_document("claims", "same") is not None


@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "needs_input", "cancelled"])
def test_status_uses_explicit_plan_not_run_events(status):
    ctx = SimpleNamespace(state={})
    update_task_plan(
        "检查资料", [{"id": "check", "title": "核对", "status": status, "detail": "需核对来源"}], tool_context=ctx
    )
    ctx.state["run_status"] = "completed"
    result = task_projection(ctx.state)
    assert result["taskStatus"] == status
    assert result["taskProgress"] == {"completed": int(status == "completed"), "total": 1}
    assert task_projection({"run_status": "completed"})["taskStatus"] == "unplanned"


def test_task_filter_is_owner_scoped_and_cursor_bound(repo, api):
    for key, values in [("a", {}), ("b", {}), ("foreign", {"ownerUid": "bob"})]:
        repo.set_document("chat_sessions", key, document(key, taskStatus="needs_input", **values))
    repo.set_document("chat_sessions", "unplanned", document("unplanned"))
    first = api.get("/api/sessions/search", params={"task_status": "needs_input", "page_size": 1}).json()
    assert [row["session_id"] for row in first["sessions"]] == ["b"]
    assert first["sessions"][0]["task_status"] == "needs_input"
    assert (
        api.get("/api/sessions/search", params={"cursor": first["next_cursor"], "task_status": "running"}).status_code
        == 400
    )
    unknown = api.get("/api/sessions/search", params={"task_status": "unplanned"}).json()
    assert [row["session_id"] for row in unknown["sessions"]] == ["unplanned"]
    assert api.get("/api/sessions/search", params={"task_status": "invented"}).status_code == 400


def test_report_save_restore_conflict_download_and_source_acl(repo, api):
    repo.set_document("chat_sessions", "mine", document("mine"))
    body = {"message_id": "answer", "title": "季度报告", "content": "初始正文", "expected_revision": 0}
    first = api.post("/api/sessions/mine/reports", json=body)
    assert first.status_code == 200, first.text
    report = first.json()
    assert report["revision"] == 1
    assert api.post("/api/sessions/mine/reports", json=body).status_code == 409
    assert api.post("/api/sessions/mine/reports", json={**body, "expected_revision": 99}).status_code == 409
    second = api.post("/api/sessions/mine/reports", json={**body, "content": "编辑后正文", "expected_revision": 1})
    assert second.json()["revision"] == 2
    saved = api.get("/api/sessions/mine/reports").json()["reports"]
    assert len(saved) == 1 and saved[0]["content"] == "编辑后正文"
    url = f"/api/sessions/mine/reports/{report['report_id']}/download"
    download = api.get(url)
    assert download.text == "编辑后正文" and download.headers["cache-control"] == "no-store"
    for other in client("bob"):
        assert other.get("/api/sessions/mine/reports").status_code == 403
        assert other.get(url).status_code == 403
        assert other.post("/api/sessions/mine/reports", json=body).status_code == 403
    repo.update_document("chat_sessions", "mine", {"accessControl": {"type": "public"}})
    for other in client("bob"):
        assert other.get(url).status_code == 200
        assert other.post("/api/sessions/mine/reports", json=body).status_code == 403


@pytest.mark.asyncio
async def test_confirmation_claim_survives_refresh_and_rejects_display_only(repo):
    idx = SimpleNamespace(owner_uid="alice", session_id="s1", app_name="root-agent")
    service = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(
                state={
                    "a2ui_surface:confirm": {"artifact": {"kind": "elicitation"}},
                    "a2ui_surface:plan": {"artifact": {"displayOnly": True}},
                }
            )
        )
    )
    with patch("protocols.action_claims.get_session_service", return_value=service):
        await claim_action(idx, "confirm", "first-tab")
        with pytest.raises(HTTPException) as duplicate:
            await claim_action(idx, "confirm", "second-tab")
        assert duplicate.value.status_code == 409
        with pytest.raises(HTTPException):
            await claim_action(idx, "plan", "other")
        await claim_action(idx, "reusable", "one")
        with pytest.raises(HTTPException):
            await claim_action(idx, "reusable", "one")
        await claim_action(idx, "reusable", "two")
