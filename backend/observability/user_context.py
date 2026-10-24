"""Trusted request identity and explicitly authorized resource ownership."""

from contextlib import contextmanager
from contextvars import ContextVar

from auth.models import User

_context: ContextVar[dict[str, str] | None] = ContextVar("user_context", default=None)


def set_user_context(user: User, extra: dict[str, str] | None = None) -> None:
    attrs = {key: value for key, value in (extra or {}).items() if not key.startswith(("user.", "resource."))}
    attrs.update({"user.id": user.uid, "user.auth_mode": user.auth_mode})
    _context.set(attrs)


def get_user_context() -> dict[str, str] | None:
    value = _context.get()
    return dict(value) if value is not None else None


def get_resource_user_id() -> str:
    attrs = _context.get() or {}
    return (attrs.get("resource.user_id") or attrs.get("user.id") or "").strip()


@contextmanager
def authorized_resource_user(user_id: str):
    """Select an owner only after a resource-specific ACL check succeeds."""
    if not user_id.strip():
        raise PermissionError("Resource owner is required")
    token = _context.set({**(_context.get() or {}), "resource.user_id": user_id.strip()})
    try:
        yield
    finally:
        _context.reset(token)


def require_resource_user(user_id: str) -> str:
    owner = get_resource_user_id()
    if not owner or owner != user_id:
        raise PermissionError("Resource belongs to another user")
    return owner
