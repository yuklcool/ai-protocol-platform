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
    tenant_id: str = "",
    actor_tenant_id: str = "",
    before: Any = None,
    after: Any = None,
) -> None:
    """Append one audit record for an admin mutation."""
    record = {
        "tenantId": tenant_id.strip().casefold(),
        "actorTenantId": actor_tenant_id.strip().casefold(),
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
    """Read by explicit target tenant; unattributed legacy rows are platform-only.

    ``domains`` is the historical parameter name for stable tenant scope keys.
    Actor identity and target strings are never used to infer ownership.
    """
    if domains is not None and not domains:
        return [], 0
    filters = None if domains is None else [("tenantId", "in", sorted(domains))]

    try:
        raw = query_documents(_COLLECTION, filters=filters, order_by="ts", order_direction="DESCENDING", limit=None)
    except Exception as exc:
        logger.error("admin_audit read FAILED: %s", exc)
        return [], 0

    # Defense in depth, also prevents cross-tenant counts from leaking.
    raw = [row for row in raw if domains is None or row.get("tenantId") in domains]
    scanned = len(raw)
    rows: list[dict[str, Any]] = []
    for row in raw:
        if action and str(row.get("action") or "") != action:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, scanned


__all__ = ["list_admin_actions", "record_admin_action"]
