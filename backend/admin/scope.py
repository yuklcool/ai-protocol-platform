"""Platform administration is independent from personal resource ownership."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException

from auth import User, get_current_user
from auth.admin_roles import is_platform_admin


@dataclass(frozen=True)
class AdminScope:
    user: User

    @property
    def is_platform(self) -> bool:
        return True

    def assert_platform(self) -> None:
        if not is_platform_admin(self.user.group_tags):
            raise HTTPException(403, "Platform admin required")


def resolve_admin_scope(user: User) -> AdminScope | None:
    return AdminScope(user=user) if is_platform_admin(user.group_tags) else None


def require_admin_scope(user: Annotated[User, Depends(get_current_user)]) -> AdminScope:
    scope = resolve_admin_scope(user)
    if scope is None:
        raise HTTPException(403, "Platform admin required")
    return scope


Scope = Annotated[AdminScope, Depends(require_admin_scope)]
PlatformScope = Scope
