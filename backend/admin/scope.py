"""Resolved admin authority for one request.

Every ``/api/admin/*`` route gates on one shared dependency answering which
stable tenant ids the caller may touch.  Tenant ids are first-class; email
domains are only legacy identity mappings.

Compatibility note
------------------
Historically this primitive exposed a field named ``domains`` and helpers such
as ``filter_domains``. Existing admin routes still use those names, so the
storage field is retained during the migration. Its values are now *tenant
scope keys* (stable tenant ids; legacy installations use their old domain as the
tenant id). New code should prefer ``tenant_ids``, ``may_tenant`` and
``filter_tenant_ids``.

Scope shapes
------------
``tenant_ids is None``             -> platform scope (``aitana-admin``)
``tenant_ids == {"tenant-acme"}`` -> exactly that tenant
no admin authority                 -> dependency returns 403 before a scope is built

Deny-by-default is structural: blank tenant ids never match and an unknown
scope never means "unscoped allow".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException

from auth import User, get_current_user
from auth.admin_roles import is_platform_admin, tenant_admin_tenant_ids


def _normalise_scope_key(value: str | None) -> str:
    """Canonicalize admin scope keys.

    Tenant ids are issued by this platform and are treated case-insensitively
    for admin claims to preserve the historical domain behavior. Operators
    should use lowercase stable ids; legacy domain ids therefore remain fully
    compatible.
    """
    return (value or "").strip().casefold()


def domain_of_key(key: str | None) -> str:
    """Legacy helper returning the email-domain ownership hint for an admin key.

    It remains for old user/tool/audit surfaces that have not yet gained an
    explicit ``tenantId``. New tenant-aware resources must carry tenantId and
    should not derive tenant ownership from arbitrary identifiers.
    """
    k = (key or "").strip().casefold()
    if not k or k == "*":
        return ""
    if "@" in k:
        return k.rsplit("@", 1)[-1]
    return k if "." in k else ""


@dataclass(frozen=True)
class AdminScope:
    """The tenants one admin caller may read or mutate.

    ``domains`` is retained as the constructor/storage name for backward
    compatibility. Its values are tenant ids. Use :attr:`tenant_ids` in new
    code. ``None`` means platform-wide authority; an empty set should never be
    constructed by :func:`resolve_admin_scope`.
    """

    user: User
    domains: frozenset[str] | None

    @property
    def tenant_ids(self) -> frozenset[str] | None:
        """Preferred first-class view of the scoped stable tenant ids."""
        return self.domains

    @property
    def is_platform(self) -> bool:
        return self.domains is None

    def may_tenant(self, tenant_id: str | None) -> bool:
        """True iff this scope covers ``tenant_id``; blank always denies."""
        target = _normalise_scope_key(tenant_id)
        if not target:
            return False
        if self.domains is None:
            return True
        return target in self.domains

    def may(self, tenant_id: str | None) -> bool:
        """Backward-compatible alias of :meth:`may_tenant`."""
        return self.may_tenant(tenant_id)

    def assert_may_tenant(self, tenant_id: str | None) -> None:
        """Raise 403 unless this scope covers ``tenant_id``."""
        if not self.may_tenant(tenant_id):
            # Deliberately do not expose the caller's scope contents.
            raise HTTPException(status_code=403, detail="Outside your tenant scope")

    def assert_may(self, tenant_id: str | None) -> None:
        """Backward-compatible alias of :meth:`assert_may_tenant`."""
        self.assert_may_tenant(tenant_id)

    def assert_platform(self) -> None:
        if not self.is_platform:
            raise HTTPException(status_code=403, detail="Platform admin required")

    def filter_tenant_ids(self, tenant_ids: object) -> list[str]:
        """Return only in-scope tenant ids, preserving input order/casing."""
        items = [str(value) for value in tenant_ids] if tenant_ids else []
        if self.domains is None:
            return items
        return [value for value in items if _normalise_scope_key(value) in self.domains]

    def filter_domains(self, domains: object) -> list[str]:
        """Legacy alias for domain-shaped tenant ids."""
        return self.filter_tenant_ids(domains)


def resolve_admin_scope(user: User) -> AdminScope | None:
    """Resolve trusted admin tags into platform or stable-tenant authority."""
    tags = user.group_tags
    if is_platform_admin(tags):
        return AdminScope(user=user, domains=None)
    tenant_ids = frozenset(
        _normalise_scope_key(value)
        for value in tenant_admin_tenant_ids(tags)
        if _normalise_scope_key(value)
    )
    if not tenant_ids:
        return None
    # ``domains`` is the compatibility storage field; semantically these are
    # first-class tenant ids.
    return AdminScope(user=user, domains=tenant_ids)


def require_admin_scope(user: Annotated[User, Depends(get_current_user)]) -> AdminScope:
    scope = resolve_admin_scope(user)
    if scope is None:
        raise HTTPException(status_code=403, detail="Administrative tenant scope required")
    return scope


def require_platform_scope(scope: Annotated[AdminScope, Depends(require_admin_scope)]) -> AdminScope:
    scope.assert_platform()
    return scope


Scope = Annotated[AdminScope, Depends(require_admin_scope)]
PlatformScope = Annotated[AdminScope, Depends(require_platform_scope)]


__all__ = [
    "AdminScope",
    "PlatformScope",
    "Scope",
    "domain_of_key",
    "require_admin_scope",
    "require_platform_scope",
    "resolve_admin_scope",
]