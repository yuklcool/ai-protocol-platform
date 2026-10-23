"""Synthetic metadata only, for the isolated Compose browser acceptance DB."""

import json
import os
import urllib.request

from db.persistence import get_repository
from tests.support.session_search import document


def main():
    tag = os.environ["SESSION_SEARCH_E2E_RUN_ID"]
    payload = json.dumps(
        {"email": os.environ["SELFHOST_ADMIN_EMAIL"], "password": os.environ["SELFHOST_ADMIN_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        "http://backend:1956/api/auth/login", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        owner = json.load(response)["user"]["uid"]
    repo = get_repository()
    for n in range(30):
        key = f"{tag}-recent-{n:02}"
        repo.set_document(
            "chat_sessions",
            key,
            document(key, owner=owner, title=f"最近任务 {tag} {n:02}", lastMessageAt="2026-10-22T12:00:00Z"),
        )
    for n in range(25):
        key = f"{tag}-match-{n:02}"
        repo.set_document(
            "chat_sessions",
            key,
            document(
                key,
                owner=owner,
                title=f"照明能耗 {tag} {n:02}",
                taskStatus="needs_input" if n == 24 else "unplanned",
                lastMessageAt="2026-10-20T12:00:00Z",
            ),
        )
    key = f"{tag}-private"
    repo.set_document("chat_sessions", key, document(key, owner=f"foreign-{tag}", title=f"照明能耗 {tag} 不可见"))
    print("Seeded 55 owned session summaries and one foreign-owner negative fixture; no transcript or model call")


if __name__ == "__main__":
    main()
