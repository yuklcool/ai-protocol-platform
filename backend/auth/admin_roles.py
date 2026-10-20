"""Administrative roles from trusted identity records."""

from collections.abc import Iterable

PLATFORM_ADMIN_TAG = "aitana-admin"
SKILL_ADMIN_TAGS = frozenset({PLATFORM_ADMIN_TAG, "one-admin"})


def is_platform_admin(group_tags: Iterable[str] | None) -> bool:
    return PLATFORM_ADMIN_TAG in (group_tags or ())


def is_skill_admin(group_tags: Iterable[str] | None) -> bool:
    return bool(set(group_tags or ()) & SKILL_ADMIN_TAGS)


def is_admin_conferring_tag(tag: str) -> bool:
    return tag.strip() in SKILL_ADMIN_TAGS
