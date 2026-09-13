"""Small backend-independent helpers for document-style repository queries."""

from __future__ import annotations

import json
from typing import Any

from db.repository import Filter


def matches_filters(data: dict[str, Any], filters: list[Filter] | None) -> bool:
    if not filters:
        return True
    for field, op, expected in filters:
        actual = data.get(field)
        if op == "==" and actual != expected:
            return False
        if op == "!=" and actual == expected:
            return False
        if op == "in" and actual not in expected:
            return False
        if op == "not-in" and actual in expected:
            return False
        if op == "array_contains" and (not isinstance(actual, list) or expected not in actual):
            return False
        if op == "array_contains_any" and (
            not isinstance(actual, list) or not any(item in actual for item in expected)
        ):
            return False
        if op == ">" and not (actual is not None and actual > expected):
            return False
        if op == ">=" and not (actual is not None and actual >= expected):
            return False
        if op == "<" and not (actual is not None and actual < expected):
            return False
        if op == "<=" and not (actual is not None and actual <= expected):
            return False
        if op not in {"==", "!=", "in", "not-in", "array_contains", "array_contains_any", ">", ">=", "<", "<="}:
            raise ValueError(f"Unsupported repository filter operator: {op!r}")
    return True


def sort_key(value: Any) -> tuple[int, Any]:
    """Stable cross-backend ordering for common JSON scalar values."""
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (2, float(value))
    if isinstance(value, str):
        return (3, value)
    return (4, json.dumps(value, sort_keys=True, default=str))


def apply_query(
    docs: list[dict[str, Any]],
    *,
    filters: list[Filter] | None = None,
    order_by: str | None = None,
    order_direction: str = "DESCENDING",
    start_after_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    result = [doc for doc in docs if matches_filters(doc, filters)]
    if order_by:
        result.sort(
            key=lambda doc: sort_key(doc.get(order_by)),
            reverse=order_direction.upper() == "DESCENDING",
        )
    if start_after_id:
        for idx, doc in enumerate(result):
            if str(doc.get("__id", "")) == start_after_id:
                result = result[idx + 1 :]
                break
    if limit is not None:
        result = result[:limit]
    return result
