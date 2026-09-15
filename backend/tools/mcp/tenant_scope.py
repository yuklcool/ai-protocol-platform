"""Stable tenant visibility policy for persisted MCP server configs.

MCP server credentials/endpoints are security-sensitive resources.  A config is
visible only when its scope is explicit:

* ``scope=platform`` — intentionally shared platform-operated server.
* ``scope=tenant`` — private to the exact non-empty ``tenantId``.

Historical rows with no scope are intentionally *not* treated as platform-wide;
they must be re-seeded or migrated.  This prevents a pre-multitenancy registry
row from silently becoming accessible to every tenant.
"""

from __future__ import annotations

from typing import Any

PLATFORM_SCOPE = "platform"
TENANT_SCOPE = "tenant"


def normalize_mcp_scope(config: dict[str, Any]) -> str:
    return str(config.get("scope") or "").strip().lower()


def mcp_config_visible_to_tenant(config: dict[str, Any] | None, tenant_id: str) -> bool:
    if not config:
        return False
    scope = normalize_mcp_scope(config)
    if scope == PLATFORM_SCOPE:
        return True
    if scope != TENANT_SCOPE:
        return False
    resource_tenant = str(config.get("tenantId") or "").strip()
    viewer_tenant = (tenant_id or "").strip()
    return bool(resource_tenant and viewer_tenant and resource_tenant == viewer_tenant)


def require_stable_tenant_id(tenant_id: str) -> str:
    value = (tenant_id or "").strip()
    if not value:
        raise PermissionError("stable tenant context is required for MCP server access")
    return value


__all__ = [
    "PLATFORM_SCOPE",
    "TENANT_SCOPE",
    "mcp_config_visible_to_tenant",
    "normalize_mcp_scope",
    "require_stable_tenant_id",
]
