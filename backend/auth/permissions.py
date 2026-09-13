"""Tool-class permission enforcement.

Permission documents are resolved through ``db.persistence`` so self-hosted
PostgreSQL deployments use the same user/domain/wildcard policy semantics as
Firestore deployments.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from db import persistence as fs

logger = logging.getLogger(__name__)

COLLECTION = "tool_permissions"
_CACHE_TTL = 60


class ToolPermissionDenied(Exception):
    """Raised when a user is not permitted to invoke a tool."""

    def __init__(self, user_email: str, tool_name: str) -> None:
        self.user_email = user_email
        self.tool_name = tool_name
        super().__init__(f"user {user_email} is not permitted to use tool {tool_name}")


_cache: dict[tuple[str, str], tuple[bool, float]] = {}


def _cache_get(email: str, tool_name: str) -> bool | None:
    key = (email, tool_name)
    entry = _cache.get(key)
    if entry is None:
        return None
    allowed, ts = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return allowed


def _cache_set(email: str, tool_name: str, allowed: bool) -> None:
    _cache[(email, tool_name)] = (allowed, time.monotonic())


def clear_cache() -> None:
    _cache.clear()


def _doc_allows(doc: dict[str, Any], tool_name: str) -> bool:
    tools: list[str] = doc.get("tools", [])
    denied: list[str] = doc.get("denied", [])
    if tool_name in denied:
        return False
    return "*" in tools or tool_name in tools


def can_use_tool(user_email: str, user_domain: str, tool_name: str) -> bool:
    """Resolve user -> domain -> wildcard permission, deny by default."""
    cached = _cache_get(user_email, tool_name)
    if cached is not None:
        return cached

    user_doc = fs.get_document(COLLECTION, user_email) if user_email else None
    if user_doc is not None:
        result = _doc_allows(user_doc, tool_name)
        _cache_set(user_email, tool_name, result)
        logger.debug("perm: user-level %s → %s for %s", user_email, result, tool_name)
        return result

    if user_domain:
        domain_doc = fs.get_document(COLLECTION, user_domain)
        if domain_doc is not None:
            result = _doc_allows(domain_doc, tool_name)
            _cache_set(user_email, tool_name, result)
            logger.debug("perm: domain-level %s → %s for %s", user_domain, result, tool_name)
            return result

    wildcard_doc = fs.get_document(COLLECTION, "*")
    if wildcard_doc is not None:
        result = _doc_allows(wildcard_doc, tool_name)
        _cache_set(user_email, tool_name, result)
        logger.debug("perm: wildcard → %s for %s", result, tool_name)
        return result

    _cache_set(user_email, tool_name, False)
    logger.debug("perm: no rule → deny %s for %s", user_email, tool_name)
    return False
