"""Request-scoped access context + pure-Python access evaluator.

Tenant isolation is a hard boundary that runs *before* ordinary sharing ACLs.
Any resource exposing a ``tenant_id`` attribute is tenant-aware: its tenant id
must be non-empty and match the authenticated context. Public/domain/tagged
sharing never crosses that boundary. Resources that have not yet migrated to a
first-class tenant field keep the historical five-type ACL behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from auth.admin_roles import is_platform_admin as _is_platform_admin_tags
from auth.admin_roles import is_skill_admin as _is_skill_admin_tags
from auth.admin_roles import is_tenant_admin as _is_tenant_admin_tags

if TYPE_CHECKING:
    from auth.models import User
    from db.models.access import AccessControl

SKILL_ADMIN_TAG = "one-admin"


@runtime_checkable
class _HasAccess(Protocol):
    access_control: AccessControl
    owner_id: str


@dataclass(frozen=True)
class AccessContext:
    """Immutable per-request access snapshot derived from a verified identity."""

    uid: str
    email: str = ""
    domain: str = ""
    tenant_id: str = ""
    group_tags: frozenset[str] = field(default_factory=frozenset)

    def _tenant_allows(self, resource: object) -> bool:
        """Hard-gate first-class tenant resources.

        ``hasattr`` is intentional: legacy resource types without a tenant field
        continue through their existing ACL path, while a migrated resource with
        an empty tenant id is unattributable and therefore denied.
        """
        if not hasattr(resource, "tenant_id"):
            return True
        resource_tenant = str(getattr(resource, "tenant_id", "") or "").strip()
        viewer_tenant = (self.tenant_id or "").strip()
        return bool(resource_tenant and viewer_tenant and resource_tenant == viewer_tenant)

    def is_owner(self, resource: _HasAccess) -> bool:
        return self._tenant_allows(resource) and bool(resource.owner_id) and resource.owner_id == self.uid

    def can_access(self, resource: _HasAccess) -> bool:
        if not self._tenant_allows(resource):
            return False
        return can_access(resource.access_control, self, resource.owner_id)

    def can_access_skill(self, skill: _HasAccess) -> bool:
        return self.can_access(skill)

    def is_skill_owner(self, skill: _HasAccess) -> bool:
        return self.is_owner(skill)

    def is_skill_admin(self, skill: _HasAccess) -> bool:
        return self.is_skill_owner(skill) or _is_skill_admin_tags(self.group_tags)

    @property
    def is_platform_admin(self) -> bool:
        return _is_platform_admin_tags(self.group_tags)

    def is_tenant_admin(self, tenant_id: str | None = None) -> bool:
        scope = (tenant_id if tenant_id is not None else self.tenant_id).strip()
        return _is_tenant_admin_tags(self.group_tags, scope)

    def can_access_folder(self, folder: object) -> bool:
        if not self._tenant_allows(folder):
            return False
        ac = getattr(folder, "effective_access", None)
        owner_id = getattr(folder, "owner_id", "")
        if ac is None:
            return False
        return can_access(ac, self, owner_id)


def build_access_context(user: User) -> AccessContext:
    tenant_id = (user.tenant_id or user.domain).strip()
    return AccessContext(
        uid=user.uid,
        email=user.email,
        domain=user.domain,
        tenant_id=tenant_id,
        group_tags=user.group_tags,
    )


def can_access(ac: AccessControl, ctx: AccessContext, owner_id: str) -> bool:
    """Pure five-type sharing evaluator. Tenant gating lives on AccessContext."""
    if ac.type == "public":
        return True
    if owner_id and owner_id == ctx.uid:
        return True
    if ac.type == "domain":
        return bool(ctx.domain) and ctx.domain == ac.domain
    if ac.type == "specific":
        return bool(ctx.email) and ctx.email in (ac.emails or [])
    if ac.type == "tagged":
        return bool(ctx.group_tags & set(ac.tags or []))
    return False


__all__ = ["AccessContext", "build_access_context", "can_access"]
