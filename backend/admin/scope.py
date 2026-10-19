"""按稳定租户 ID 解析管理权限。邮箱域仅用于身份映射, 不参与租户授权。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException

from auth import User, get_current_user
from auth.admin_roles import is_platform_admin, tenant_admin_tenant_ids


def _normalise_scope_key(value: str | None) -> str:
    """稳定租户 ID 精确匹配, 不应用域名的小写兼容规则。"""
    return (value or "").strip()


@dataclass(frozen=True)
class AdminScope:
    """One admin caller's exact stable tenant IDs; None means platform authority."""

    user: User
    tenant_ids: frozenset[str] | None

    @property
    def is_platform(self) -> bool:
        return self.tenant_ids is None

    def may_tenant(self, tenant_id: str | None) -> bool:
        """True iff this scope covers ``tenant_id``; blank always denies."""
        target = _normalise_scope_key(tenant_id)
        if not target:
            return False
        if self.tenant_ids is None:
            return True
        return target in self.tenant_ids

    def assert_may_tenant(self, tenant_id: str | None) -> None:
        """Raise 403 unless this scope covers ``tenant_id``."""
        if not self.may_tenant(tenant_id):
            # Deliberately do not expose the caller's scope contents.
            raise HTTPException(status_code=403, detail="Outside your tenant scope")

    def assert_platform(self) -> None:
        if not self.is_platform:
            raise HTTPException(status_code=403, detail="Platform admin required")

    def filter_tenant_ids(self, tenant_ids: object) -> list[str]:
        """Return only in-scope tenant ids, preserving input order/casing."""
        items = [str(value) for value in tenant_ids] if tenant_ids else []
        if self.tenant_ids is None:
            return items
        return [value for value in items if _normalise_scope_key(value) in self.tenant_ids]


def resolve_admin_scope(user: User) -> AdminScope | None:
    """Resolve trusted admin tags into platform or stable-tenant authority."""
    tags = user.group_tags
    if is_platform_admin(tags):
        return AdminScope(user=user, tenant_ids=None)
    tenant_ids = frozenset(
        _normalise_scope_key(value) for value in tenant_admin_tenant_ids(tags) if _normalise_scope_key(value)
    )
    if not tenant_ids:
        return None
    return AdminScope(user=user, tenant_ids=tenant_ids)


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
    "require_admin_scope",
    "require_platform_scope",
    "resolve_admin_scope",
]
