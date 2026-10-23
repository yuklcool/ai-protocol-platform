import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db.firestore_inmemory import InMemoryFirestoreClient
from db.persistence import reset_repository_for_testing
from db.repositories.firestore import FirestoreRepository
from db.repositories.memory import MemoryRepository
from db.session_search import SessionSearch, search_sessions
from protocols.sessions_route import router
from tests.support.session_search import client, document


@pytest.fixture(params=[MemoryRepository, FirestoreRepository])
def repo(request):
    value = request.param(client=InMemoryFirestoreClient())
    reset_repository_for_testing(value)
    return value


@pytest.fixture
def api(repo):
    yield from client()


def test_search_before_pagination_reaches_older_matches_and_excludes_hidden_rows(repo, api):
    for number in range(120):
        repo.set_document("chat_sessions", f"draft-{number}", document(f"draft-{number}", provisional=True))
        repo.set_document("chat_sessions", f"new-{number}", document(f"new-{number}", title="unrelated"))
    for number in range(25):
        key = f"match-{number:02}"
        repo.set_document("chat_sessions", key, document(key, lastMessageAt="2026-10-01T00:00:00Z"))
    repo.set_document("chat_sessions", "foreign", document("foreign", owner="bob"))
    repo.set_document("chat_sessions", "archived", document("archived", archivedAt="2026-10-22T00:00:00Z"))
    first = api.get("/api/sessions/search", params={"q": "ENERGY", "owner_uid": "bob"}).json()
    assert [s["session_id"] for s in first["sessions"]] == [f"match-{n:02}" for n in range(24, 4, -1)]
    second = api.get("/api/sessions/search", params={"q": "energy", "cursor": first["next_cursor"]}).json()
    assert [s["session_id"] for s in second["sessions"]] == [f"match-{n:02}" for n in range(4, -1, -1)]
    assert second["next_cursor"] is None


def test_cursor_survives_anchor_deletion_and_rejects_foreign_owner_or_changed_filter(repo, api):
    for key in ("a", "b", "c"):
        repo.set_document("chat_sessions", key, document(key))
    first = api.get("/api/sessions/search", params={"page_size": 1}).json()
    cursor = first["next_cursor"]
    repo.delete_document("chat_sessions", "c")
    page = api.get("/api/sessions/search", params={"page_size": 1, "cursor": cursor}).json()
    assert [s["session_id"] for s in page["sessions"]] == ["b"]
    assert api.get("/api/sessions/search", params={"q": "changed", "cursor": cursor}).status_code == 400
    for foreign in client("bob"):
        assert foreign.get("/api/sessions/search", params={"cursor": cursor}).status_code == 400


def test_literal_substring_chinese_and_timezone_aware_date_range(repo, api):
    repo.set_document(
        "chat_sessions", "a", document("a", title="照明 %_ quote'", lastMessageAt="2026-10-19T17:00:00-07:00")
    )
    repo.set_document("chat_sessions", "b", document("b", lastMessageAt="2026-10-21T00:00:00Z", skillId="other"))
    repo.set_document("chat_sessions", "c", document("c", title=None, lastMessageAt="2026-10-19T00:00:00Z"))
    for query in ("照明 %_", "quote'", "a"):
        data = api.get(
            "/api/sessions/search",
            params={"q": query, "updated_after": "2026-10-20T08:00:00+08:00", "updated_before": "2026-10-21T00:00:00Z"},
        ).json()
        assert [s["session_id"] for s in data["sessions"]] == ["a"]
    assert [
        s["session_id"] for s in api.get("/api/sessions/search", params={"skill_id": "other"}).json()["sessions"]
    ] == ["b"]
    assert api.get("/api/sessions/search", params={"q": "%"}).json()["next_cursor"] is None
    assert api.get("/api/sessions/search", params={"q": "does not exist"}).json()["sessions"] == []


def test_malformed_metadata_does_not_truncate_pagination(repo, api):
    for key in ("a", "b", "c", "d", "e"):
        repo.set_document(
            "chat_sessions", key, document(key, accessControl="invalid" if key in {"d", "c"} else {"type": "private"})
        )
    first = api.get("/api/sessions/search", params={"page_size": 2}).json()
    assert [s["session_id"] for s in first["sessions"]] == ["e", "b"]
    second = api.get("/api/sessions/search", params={"page_size": 2, "cursor": first["next_cursor"]}).json()
    assert [s["session_id"] for s in second["sessions"]] == ["a"]
    assert second["next_cursor"] is None


@pytest.mark.parametrize(
    "params, status",
    [
        ({"q": "a" * 201}, 422),
        ({"cursor": "!invalid"}, 400),
        ({"page_size": 0}, 422),
        ({"updated_after": "2026-10-23T00:00:00"}, 422),
        ({"updated_after": "2026-10-23T00:00:00Z", "updated_before": "2026-10-22T00:00:00Z"}, 400),
        ({"cursor": base64.urlsafe_b64encode(json.dumps([]).encode()).decode()}, 400),
    ],
)
def test_invalid_search_never_silently_restarts_at_first_page(api, params, status):
    assert api.get("/api/sessions/search", params=params).status_code == status


def test_requires_authentication_and_trusted_resource_owner(repo):
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/api/sessions/search").status_code in (401, 403)
    with pytest.raises(PermissionError):
        search_sessions(SessionSearch(owner_uid="alice"))
