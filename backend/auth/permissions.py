"""Tool-class permission enforcement.

Permission documents are resolved through ``db.persistence`` so self-hosted
PostgreSQL deployments use the same policy semantics as Firestore deployments.

The first-class lookup order is user -> stable tenant -> legacy domain ->
wildcard. Stable tenant identity is recovered from the auth-bound task context;
callers do not supply an untrusted tenant id. Legacy user/domain rules remain a
migration bridge, but they are never allowed to cross an explicit stable tenant
boundary.
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


def _normalise_domain(value: str) -> str:
    return (value or "").strip().casefold().rstrip(".")


def _legacy_domain_belongs_to_tenant(domain: str, stable_tenant: str) -> bool:
    """Whether one legacy domain rule is safe inside the stable tenant scope."""
    normalized = _normalise_domain(domain)
    if not normalized:
        return False
    if not stable_tenant:
        # No first-class request context: preserve the historical lookup path.
        return True
    if normalized == stable_tenant:
        # Legacy installs used the email domain itself as the tenant id.
        return True
    try:
        from db.tenants import tenant_id_for_domain

        return str(tenant_id_for_domain(normalized) or "").strip() == stable_tenant
    except Exception as exc:
        logger.debug("perm: tenant-domain ownership lookup failed for %s: %s", normalized, exc)
        return False


def _user_rule_matches_tenant(doc: dict[str, Any], stable_tenant: str, user_domain: str) -> bool:
    """Prevent an email-keyed rule from leaking across stable tenant identity."""
    owner = str(doc.get("tenantId") or "").strip()
    if owner:
        return bool(stable_tenant) and owner == stable_tenant
    if not stable_tenant:
        # Pure legacy path: there is no stable tenant boundary to enforce yet.
        return True
    # Unattributed legacy user rules remain usable only while the stable tenant
    # is still the historical domain id. Once a domain maps to an opaque stable
    # id, migration must explicitly attribute the user rule before it can win.
    return stable_tenant == _normalise_domain(user_domain)


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
        if _user_rule_matches_tenant(user_doc, stable_tenant, user_domain):
            result = _doc_allows(user_doc, tool_name)
            _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
            logger.debug("perm: user-level %s tenant=%s → %s for %s", user_email, stable_tenant, result, tool_name)
            return result
        logger.debug(
            "perm: skipping user-level %s because rule ownership does not match tenant=%s",
            user_email,
            stable_tenant,
        )

    tenant_key = tenant_permission_key(stable_tenant)
    if tenant_key:
        tenant_doc = fs.get_document(COLLECTION, tenant_key)
        if tenant_doc is not None:
            owner = str(tenant_doc.get("tenantId") or stable_tenant).strip()
            if owner != stable_tenant:
                logger.warning(
                    "perm: ignoring malformed tenant rule %s with tenantId=%s",
                    tenant_key,
                    owner,
                )
            else:
                result = _doc_allows(tenant_doc, tool_name)
                _cache_set(user_email, stable_tenant, user_domain, tool_name, result)
                logger.debug("perm: tenant-level %s → %s for %s", stable_tenant, result, tool_name)
                return result

    if user_domain and _legacy_domain_belongs_to_tenant(user_domain, stable_tenant):
        domain_doc = fs.get_document(COLLECTION, user_domain)
        if domain_doc is not None:
            explicit_owner = str(domain_doc.get("tenantId") or "").strip()
            if explicit_owner and stable_tenant and explicit_owner != stable_tenant:
                logger.warning(
                    "perm: ignoring legacy domain rule %s with conflicting tenantId=%s",
                    user_domain,
                    explicit_owner,
                )
            else:
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
