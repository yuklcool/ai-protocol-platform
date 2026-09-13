"""Append-only admin audit trail.

Audit persistence is backend-neutral: memory, Firestore, and PostgreSQL all use
the same document contract through ``db.persistence``. Writes remain best-effort
so an audit-store outage is observable but does not fail the admin mutation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from db.persistence import query_documents, set_document

logger = logging.getLogger(__name__)

_COLLECTION = "admin_audit"


def record_admin_action(
    *,
    actor_uid: str,
    action: str,
    target: str,
    actor_email: str = "",
    before: Any = None,
    after: Any = None,
) -> None:
    """Append one audit record for an admin mutation."""
    record = {
        "actorUid": actor_uid,
        "actorEmail": actor_email,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "ts": datetime.now(UTC).isoformat(),
    }
    try:
        set_document(_COLLECTION, str(uuid.uuid4()), record)
    except Exception as exc:
        logger.error(
            "admin_audit write FAILED (action=%s target=%s actor=%s): %s",
            action,
            target,
            actor_uid,
            exc,
        )


def list_admin_actions(
    *,
    domains: frozenset[str] | None,
    limit: int = 100,
    action: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Read the audit trail scoped to the caller's administered domains."""
    from admin.scope import domain_of_key

    try:
        raw = query_documents(_COLLECTION, order_by="ts", order_direction="DESCENDING", limit=None)
    except Exception as exc:
        logger.error("admin_audit read FAILED: %s", exc)
        return [], 0

    scanned = len(raw)
    rows: list[dict[str, Any]] = []
    for row in raw:
        if action and str(row.get("action") or "") != action:
            continue
        if domains is not None:
            target_domain = domain_of_key(str(row.get("target") or ""))
            if not target_domain or target_domain not in domains:
                continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, scanned


__all__ = ["list_admin_actions", "record_admin_action"]
