"""Versioned text reports on the existing document repository.

Immutable revisions make competing saves conflict across processes, not silently
overwrite each other. Routes must check the source session ACL before every read.
"""

import hashlib
from datetime import UTC, datetime

from db.persistence import get_repository

COLLECTION = "session_report_versions"


def report_key(session_id: str, message_id: str) -> str:
    return hashlib.sha256(f"{session_id}\0{message_id}".encode()).hexdigest()


def list_reports(session_id: str) -> list[dict]:
    rows = get_repository().query_documents(COLLECTION, filters=[("sessionId", "==", session_id)])
    latest: dict[str, dict] = {}
    for row in rows:
        key = row["report_id"]
        if key not in latest or latest[key]["revision"] < row["revision"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda row: row["updated_at"], reverse=True)


def save_report(session_id: str, owner_uid: str, message_id: str, title: str, content: str, revision: int) -> dict:
    key = report_key(session_id, message_id)
    current = next((row for row in list_reports(session_id) if row["report_id"] == key), None)
    if (current["revision"] if current else 0) != revision:
        raise ValueError("Report changed. Reload the saved version before saving again.")
    row = {
        "report_id": key,
        "sessionId": session_id,
        "ownerUid": owner_uid,
        "message_id": message_id,
        "title": title,
        "content": content,
        "revision": revision + 1,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if not get_repository().create_document(COLLECTION, f"{key}:{revision + 1}", row):
        raise ValueError("Report changed. Reload the saved version before saving again.")
    return row
