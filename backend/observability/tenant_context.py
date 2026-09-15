"""Per-request stable tenant context for isolation and OTel attribution.

``set_tenant_context(user)`` is called once after authentication.  The context
is task-local, so nested business code can recover the trusted stable tenant id
without re-parsing email domains or untrusted request fields.

Only non-PII identity attributes are stored. Raw email/display names never land
on spans; ``tenant.uid_hash`` remains a one-way correlation value.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from contextvars import ContextVar

from auth.firebase_auth import User

logger = logging.getLogger(__name__)

_tenant_context: ContextVar[dict[str, str] | None] = ContextVar("tenant_context", default=None)

TenantEnricher = Callable[[User], dict[str, str]]
_registered_enrichers: list[TenantEnricher] = []


def register_tenant_enricher(fn: TenantEnricher) -> None:
    if not callable(fn):
        raise TypeError(f"register_tenant_enricher requires a callable; got {type(fn).__name__}")
    _registered_enrichers.append(fn)


def clear_tenant_enrichers() -> None:
    _registered_enrichers.clear()


def set_tenant_context(user: User, extra: dict[str, str] | None = None) -> None:
    """Bind trusted tenant attributes to the current async task.

    ``tenant.id`` is the stable authorization/persistence scope. Domain is only
    a migration fallback for legacy identities that predate explicit tenant
    claims; new local-JWT/OIDC identities should populate ``User.tenant_id``.
    """
    stable_tenant_id = (getattr(user, "tenant_id", "") or user.domain or "").strip()
    attrs: dict[str, str] = {
        "tenant.uid": user.uid,
        "tenant.auth_mode": user.auth_mode,
    }
    if stable_tenant_id:
        attrs["tenant.id"] = stable_tenant_id
    if user.group_id:
        attrs["tenant.group_id"] = user.group_id
    if user.email:
        attrs["tenant.uid_hash"] = _hash_email(user.email)

    for fn in _registered_enrichers:
        try:
            attrs.update(fn(user))
        except Exception as exc:
            logger.warning(
                "tenant_context: enricher %s raised — skipping. Other enrichers continue. Error: %s",
                getattr(fn, "__name__", repr(fn)),
                exc,
            )

    if extra:
        attrs.update(extra)
    _tenant_context.set(attrs)


def get_tenant_context() -> dict[str, str] | None:
    return _tenant_context.get()


def get_current_tenant_id() -> str:
    """Return the trusted stable tenant id for the current request task.

    Empty means no authenticated tenant context is bound. Persistence helpers
    use this to fail closed rather than inventing a scope.
    """
    ctx = _tenant_context.get() or {}
    return (ctx.get("tenant.id") or "").strip()


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


__all__ = [
    "TenantEnricher",
    "clear_tenant_enrichers",
    "get_current_tenant_id",
    "get_tenant_context",
    "register_tenant_enricher",
    "set_tenant_context",
]
