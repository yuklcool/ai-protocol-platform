"""Unified admin-role model (v6.9.0 / 9.1).

Single source of truth for "who is an admin", replacing four divergent
definitions that could silently diverge.

The model is driven entirely by **trusted group-tag claims**. Tenant authority
is keyed by a stable tenant id, not by an email domain:

  - ``aitana-admin``              — PLATFORM super-admin: every tenant.
  - ``tenant-admin:{tenant_id}``  — TENANT admin: exactly that tenant.
  - ``one-admin``                 — legacy cross-skill management capability,
                                    not platform authority.

Historical deployments used a domain in the suffix
(``tenant-admin:acme.example``). That remains valid because migrated tenants
default their stable id to the old domain until operators explicitly remap it.
"""

from __future__ import annotations

from collections.abc import Iterable

PLATFORM_ADMIN_TAG = "aitana-admin"
TENANT_ADMIN_PREFIX = "tenant-admin:"
SKILL_ADMIN_TAGS = frozenset({PLATFORM_ADMIN_TAG, "one-admin"})


def _as_set(group_tags: Iterable[str] | None) -> frozenset[str]:
    """Normalise any tags iterable (frozenset/list/None) to a frozenset."""
    if not group_tags:
        return frozenset()
    return frozenset(str(t) for t in group_tags)


def is_platform_admin(group_tags: Iterable[str] | None) -> bool:
    """True iff the caller holds the platform super-admin tag."""
    return PLATFORM_ADMIN_TAG in _as_set(group_tags)


def tenant_admin_tenant_ids(group_tags: Iterable[str] | None) -> frozenset[str]:
    """Stable tenant ids granted by ``tenant-admin:{tenant_id}`` tags.

    A platform admin is implicitly an admin of every tenant, which cannot be
    enumerated by this set; use :func:`is_tenant_admin` for an actual check.
    Empty suffixes are ignored so ``tenant-admin:`` never grants authority.
    """
    tags = _as_set(group_tags)
    return frozenset(
        suffix
        for tag in tags
        if tag.startswith(TENANT_ADMIN_PREFIX)
        and (suffix := tag[len(TENANT_ADMIN_PREFIX) :].strip())
    )


def tenant_admin_domains(group_tags: Iterable[str] | None) -> frozenset[str]:
    """Backward-compatible alias for pre-tenant-id call sites.

    The returned suffixes are tenant ids. Legacy tenants whose ids are domains
    therefore continue to behave exactly as before.
    """
    return tenant_admin_tenant_ids(group_tags)


def is_tenant_admin(group_tags: Iterable[str] | None, tenant_id: str) -> bool:
    """True iff the caller may administer ``tenant_id``.

    Platform admins administer every non-empty tenant. Tenant admins match the
    exact stable tenant-id suffix. The comparison is intentionally exact: a
    tenant id is an opaque identifier, not a DNS suffix or substring.
    """
    tags = _as_set(group_tags)
    if is_platform_admin(tags):
        return bool((tenant_id or "").strip())
    target = (tenant_id or "").strip()
    if not target:
        return False
    return f"{TENANT_ADMIN_PREFIX}{target}" in tags


def is_skill_admin(group_tags: Iterable[str] | None) -> bool:
    """True iff the caller may manage skills they do not own."""
    return bool(_as_set(group_tags) & SKILL_ADMIN_TAGS)


def is_admin_conferring_tag(tag: str) -> bool:
    """True iff granting ``tag`` hands someone administrative authority."""
    t = (tag or "").strip()
    if not t:
        return False
    if t in SKILL_ADMIN_TAGS:
        return True
    return t.startswith(TENANT_ADMIN_PREFIX)


__all__ = [
    "PLATFORM_ADMIN_TAG",
    "SKILL_ADMIN_TAGS",
    "TENANT_ADMIN_PREFIX",
    "is_admin_conferring_tag",
    "is_platform_admin",
    "is_skill_admin",
    "is_tenant_admin",
    "tenant_admin_domains",
    "tenant_admin_tenant_ids",
]