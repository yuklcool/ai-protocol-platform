"""Real PostgreSQL + production metadata route, no external Provider calls."""

import os
import uuid

import pytest

from db.persistence import reset_repository_for_testing
from db.repositories.postgres import PostgresRepository
from tests.support.session_search import client, document


def test_owner_filtered_sql_search_dates_keyset_and_reconstruction():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL required for PostgreSQL search acceptance")
    repo = PostgresRepository(url)
    reset_repository_for_testing(repo)
    prefix = uuid.uuid4().hex
    owner = f"search-{prefix}"
    ids = []

    def seed(suffix, **values):
        key = f"{prefix}-{suffix}"
        ids.append(key)
        repo.set_document("chat_sessions", key, document(key, owner=owner, **values))
        return key

    try:
        matching_title = "照明 ENERGY %_ ' report"
        for n in range(100):
            seed(f"draft-{n}", provisional=True, title=matching_title)
            seed(f"new-{n}", title="unrelated", lastMessageAt="2026-10-22T00:00:00Z")
        expected = [
            seed(f"hit-{n:02}", title=matching_title, lastMessageAt="2026-10-19T17:00:00-07:00") for n in range(25)
        ]
        # Every negative matches the keyword. Only ownership / lifecycle /
        # timestamp predicates may remove it, not an unrelated title.
        seed("foreign", ownerUid="other-user", title=matching_title)
        seed("archived", archivedAt="2026-10-23T00:00:00Z", title=matching_title)
        seed("end-exclusive", lastMessageAt="2026-10-21T00:00:00Z", title=matching_title)
        for api in client(owner):
            filters = {
                "q": "energy %_ '",
                "updated_after": "2026-10-20T08:00:00+08:00",
                "updated_before": "2026-10-21T00:00:00Z",
            }
            first = api.get("/api/sessions/search", params=filters)
            assert first.status_code == 200, first.text
            data = first.json()
            assert [s["session_id"] for s in data["sessions"]] == expected[::-1][:20]
            cursor = data["next_cursor"]
            repo.delete_document("chat_sessions", expected[::-1][19])
            repo._runner.run(repo._pool.close())
            repo = PostgresRepository(url)
            reset_repository_for_testing(repo)
            second = api.get("/api/sessions/search", params={**filters, "cursor": cursor}).json()
            assert [s["session_id"] for s in second["sessions"]] == expected[::-1][20:]
            assert second["next_cursor"] is None
            assert api.get("/api/sessions/search", params={"q": "changed", "cursor": cursor}).status_code == 400
        for api in client("other-user"):
            assert api.get("/api/sessions/search", params={**filters, "cursor": cursor}).status_code == 400
    finally:
        for key in ids:
            repo.delete_document("chat_sessions", key)
        repo._runner.run(repo._pool.close())
