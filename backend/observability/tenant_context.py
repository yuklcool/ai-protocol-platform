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

# These fields are authorization/storage identity and must only come from the
# already-verified User object. Observability enrichers and caller-supplied
# ``extra`` metadata may add attributes, but may never rewrite this boundary.
_RESERVED_IDENTITY_KEYS = frozenset(
    {
        "tenant.id",
        "tenant.uid",
        "tenant.auth_mode",
        "tenant.group_id",
        "tenant.uid_hash",
    }
)


def register_tenant_enricher(fn: TenantEnricher) -> None:
    if not callable(fn):
        raise TypeError(f"register_tenant_enricher requires a callable; got {type(fn).__name__}")
    _registered_enrichers.append(fn)


def clear_tenant_enrichers() -> None:
    _registered_enrichers.clear()


def _merge_untrusted_metadata(attrs: dict[str, str], values: dict[str, str] | None) -> None:
    """Merge observability metadata without allowing identity-key override."""
    if not values:
        return
    for key, value in values.items():
        if key in _RESERVED_IDENTITY_KEYS:
            logger.warning("tenant_context: ignored attempted override of reserved key %s", key)
            continue
        attrs[key] = value


def set_tenant_context(user: User, extra: dict[str, str] | None = None) -> None:
    """Bind trusted tenant attributes to the current async task.

    ``tenant.id`` is the stable authorization/persistence scope. Domain is only
    a migration fallback for legacy identities that predate explicit tenant
    claims; new local-JWT/OIDC identities should populate ``User.tenant_id``.

    Registered enrichers are observability-only. They are deliberately unable
    to override stable identity fields; doing so could collapse two explicit
    tenants that happen to share a legacy domain mapping.
    """
    stable_tenant_id = (getattr(user, "tenant_id", "") or user.domain or "").strip()
    attrs: dict[str, str] = {}

    for fn in _registered_enrichers:
        try:
            _merge_untrusted_metadata(attrs, fn(user))
        except Exception as exc:
            logger.warning(
                "tenant_context: enricher %s raised — skipping. Other enrichers continue. Error: %s",
                getattr(fn, "__name__", repr(fn)),
                exc,
            )

    _merge_untrusted_metadata(attrs, extra)

    # Trusted verified identity is written last. Even if a future refactor
    # accidentally weakens the merge helper, these values still win.
    attrs["tenant.uid"] = user.uid
    attrs["tenant.auth_mode"] = user.auth_mode
    if stable_tenant_id:
        attrs["tenant.id"] = stable_tenant_id
    if user.group_id:
        attrs["tenant.group_id"] = user.group_id
    if user.email:
        attrs["tenant.uid_hash"] = _hash_email(user.email)

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
