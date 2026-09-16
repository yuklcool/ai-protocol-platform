"""Tool-class permission enforcement.

Permission documents are resolved through ``db.persistence`` so self-hosted
PostgreSQL deployments use the same policy semantics as Firestore deployments.

The first-class lookup order is user -> stable tenant -> legacy domain ->
wildcard. Stable tenant identity is recovered from the auth-bound task context;
callers do not supply an untrusted tenant id. The legacy domain rung remains
only as a migration bridge for existing installations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from db import persistence as fs

logger = logging.getLogger(__name__)

COLLECTION = "tool_permissions"
_CACHE_TTL = 60
TENANT_PREFIX = "tenant:"


class ToolPermissionDenied(Exception):
    """Raised when a user is not permitted to invoke a tool."""

    def __init__(self, user_email: str, tool_name: str) -> None:
        self.user_email = user_email
        self.tool_name = tool_name
        super().__init__(f"user {user_email} is not permitted to use tool {tool_name}")


# Cache includes the stable tenant/domain scope. The same email can legitimately
# appear in two tenant identities during migrations or external IdP setups; an
# email-only cache key would let one tenant's decision bleed into another.
_cache: dict[tuple[str, str, str, str], tuple[bool, float]] = {}


def tenant_permission_key(tenant_id: str) -> str:
    stable = (tenant_id or "").strip()
    return f"{TENANT_PREFIX}{stable}" if stable else ""


def _trusted_tenant_id() -> str:
    # Lazy import avoids pulling auth/observability provider code merely by
    # importing the permission module during startup or unit tests.
    try:
        from observability.tenant_context import get_current_tenant_id

        return get_current_tenant_id()
    except Exception:
        return ""


def _cache_get(email: str, tenant_id: str, domain: str, tool_name: str) -> bool | None:
    key = (email, tenant_id, domain, tool_name)
    entry = _cache.get(key)
    if entry is None:
        return None
    allowed, ts = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return allowed


def _cache_set(email: str, tenant_id: str, domain: str, tool_name: str, allowed: bool) -> None:
    _cache[(email, tenant_id, domain, tool_name)] = (allowed, time.monotonic())


def clear_cache() -> None:
    _cache.clear()


def _doc_allows(doc: dict[str, Any], tool_name: str) -> bool:
    tools: list[str] = doc.get("tools", [])
    denied: list[str] = doc.get("denied", [])
    if tool_name in denied:
        return False
    return "*" in tools or tool_name in tools


def can_use_tool(
    user_email: str,
    user_domain: str,
    tool_name: str,
    *,
    tenant_id: str | None = None,
) -> bool:
    """Resolve user -> tenant -> legacy domain -> wildcard, deny by default.

    ``tenant_id=None`` means use the trusted task-local tenant context bound by
    authentication. Passing an explicit value is intended for deterministic
    tests/internal migration verification; request payloads must never be wired
    directly to this argument.
    """
    stable_tenant = _trusted_tenant_id() if tenant_id is None else (tenant_id or "").strip()
    cached = _cache_get(user_email, stable_tenant, user_domain, tool_name)
    if cached is not None:
        return cached

    user_doc = fs.get_document(COLLECTION, user_email) if user_email else None
    if user_doc is not None:
        result = _doc_allows(user_doc, tool_name)
        _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
        logger.debug("perm: user-level %s → %s for %s", user_email, result, tool_name)
        return result

    tenant_key = tenant_permission_key(stable_tenant)
    if tenant_key:
        tenant_doc = fs.get_document(COLLECTION, tenant_key)
        if tenant_doc is not None:
            result = _doc_allows(tenant_doc, tool_name)
            _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
            logger.debug("perm: tenant-level %s → %s for %s", stable_tenant, result, tool_name)
            return result

    if user_domain:
        domain_doc = fs.get_document(COLLECTION, user_domain)
        if domain_doc is not None:
            result = _doc_allows(domain_doc, tool_name)
            _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
            logger.debug("perm: legacy domain-level %s → %s for %s", user_domain, result, tool_name)
            return result

    wildcard_doc = fs.get_document(COLLECTION, "*")
    if wildcard_doc is not None:
        result = _doc_allows(wildcard_doc, tool_name)
        _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
        logger.debug("perm: wildcard → %s for %s", result, tool_name)
        return result

    _cache_set(user_email, stable_tenant, user_domain, tool_name, False)
    logger.debug("perm: no rule → deny %s for %s", user_email, tool_name)
    return False
