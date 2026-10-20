"""Durable usage accounting grouped by users and models."""

import time

from fastapi import APIRouter, Query

from admin.scope import Scope
from db.persistence import get_repository
from observability.usage import COLLECTION

router = APIRouter(prefix="/usage", tags=["admin-usage"])


def _stats(rows: list[dict]) -> dict:
    return {
        "calls": len(rows),
        "inputTokens": sum(int(row.get("inputTokens") or 0) for row in rows),
        "outputTokens": sum(int(row.get("outputTokens") or 0) for row in rows),
        "estimatedCostUsd": sum(float(row.get("estimatedCostUsd") or 0) for row in rows),
        "unpricedCalls": sum(not row.get("pricingKnown", False) for row in rows),
    }


@router.get("")
def usage_summary(scope: Scope, user_id: str = "", days: int = Query(default=30, ge=1, le=366)) -> dict:
    filters = [("createdAt", ">=", time.time() - days * 86400)]
    if user_id:
        filters.append(("userId", "==", user_id))
    rows = get_repository().query_documents(COLLECTION, filters=filters, limit=None)
    users = [
        {"userId": uid, **_stats([row for row in rows if row.get("userId") == uid])}
        for uid in sorted({str(row.get("userId") or "") for row in rows})
    ]
    models = [
        {"modelId": model, **_stats([row for row in rows if row.get("modelId") == model])}
        for model in sorted({str(row.get("modelId") or "") for row in rows})
    ]
    return {
        "days": days,
        "totals": _stats(rows),
        "users": users,
        "models": models,
        "costBasis": "estimated",
        "historyStartsWithAccounting": True,
    }
