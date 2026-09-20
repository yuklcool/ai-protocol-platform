"""Skill configuration — backend-neutral CRUD for the skills collection.

All reads go through an in-memory cache (60s TTL) for hot skills. Persistence
is selected by ``db.persistence`` (memory / Firestore / PostgreSQL), so Skill
management no longer hard-depends on Firestore.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from db import persistence as fs
from db.models import SkillConfig

logger = logging.getLogger(__name__)

COLLECTION = "skills"
_CACHE_TTL = 60  # seconds

# Skills tagged `system` are platform-embedded agents (Skill Studio copilot,
# future help assistants): a host surface mounts them directly by slug, so they
# are excluded from browse/discovery listings (marketplace; the frontend skill
# switcher applies the same rule). Not an access gate — that stays accessControl.
SYSTEM_TAG = "system"

# Simple in-memory cache: skill_id → (timestamp, SkillConfig)
_cache: dict[str, tuple[float, SkillConfig]] = {}


def _to_firestore(config: SkillConfig) -> dict[str, Any]:
    """Serialize a SkillConfig to a document-store-compatible dict."""
    return config.model_dump(by_alias=True)


def _from_firestore(data: dict[str, Any]) -> SkillConfig:
    """Deserialize a persisted skill document to a SkillConfig."""
    data.pop("__id", None)
    return SkillConfig.model_validate(data)


def _configs_from_docs(docs: list[dict[str, Any]]) -> list[SkillConfig]:
    """Deserialize a batch of skill docs, skipping any that fail validation.

    A list read must never let one malformed document 500 the whole endpoint —
    that blanks the SkillsBar switcher for every user (see deploy-skill Trap 22).
    So we skip + log the offender loudly and return the valid remainder. The
    fix for the underlying corruption belongs on the write path (`update_skill`
    validates before persisting) and the length caps in `db.models`.
    """
    configs: list[SkillConfig] = []
    for doc in docs:
        skill_id = doc.get("__id") or doc.get("skillId") or "<unknown>"
        try:
            configs.append(_from_firestore(doc))
        except Exception as exc:
            logger.warning("skill_config: skipping invalid skill doc %s: %s", skill_id, exc)
    return configs


def _cache_get(skill_id: str) -> SkillConfig | None:
    entry = _cache.get(skill_id)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    if entry:
        del _cache[skill_id]
    return None


def _cache_set(skill_id: str, config: SkillConfig) -> None:
    _cache[skill_id] = (time.time(), config)


def _cache_invalidate(skill_id: str) -> None:
    _cache.pop(skill_id, None)
    from protocols.a2a import invalidate_cache as _invalidate_a2a_card
    from protocols.mcp_server import rebuild_tools as _rebuild_mcp_tools

    _invalidate_a2a_card()
    _rebuild_mcp_tools()


# === CRUD operations ===


def create_skill(
    name: str,
    description: str = "",
    instructions: str = "",
    owner_email: str = "",
    owner_id: str = "",
    tenant_id: str = "",
    **kwargs: Any,
) -> SkillConfig:
    """Create a new skill and persist it through the selected backend."""
    skill_id = str(uuid.uuid4())
    now = time.time()
    config = SkillConfig(
        skillId=skill_id,
        name=name,
        description=description,
        instructions=instructions,
        ownerEmail=owner_email,
        ownerId=owner_id,
        tenantId=tenant_id,
        createdAt=now,
        updatedAt=now,
        **kwargs,
    )
    fs.set_document(COLLECTION, skill_id, _to_firestore(config))
    _cache_set(skill_id, config)
    from protocols.a2a import invalidate_cache as _invalidate_a2a_card
    from protocols.mcp_server import rebuild_tools as _rebuild_mcp_tools

    _invalidate_a2a_card()
    _rebuild_mcp_tools()
    return config


def get_skill(skill_id: str) -> SkillConfig | None:
    """Get a skill by ID. Returns None if not found."""
    cached = _cache_get(skill_id)
    if cached:
        return cached

    data = fs.get_document(COLLECTION, skill_id)
    if data is None:
        return None

    config = _from_firestore(data)
    _cache_set(skill_id, config)
    return config


def find_by_slug(owner_id: str, slug: str) -> SkillConfig | None:
    """Resolve (owner_id, slug) -> SkillConfig via the repository query API."""
    docs = fs.query_documents(
        COLLECTION,
        filters=[("ownerId", "==", owner_id), ("slug", "==", slug)],
        limit=1,
    )
    if not docs:
        return None
    config = _from_firestore(docs[0])
    _cache_set(config.skill_id, config)
    return config


def resolve_skill_ref(ref: str, caller_uid: str | None = None) -> SkillConfig | None:
    """Resolve a skill reference that may be a canonical id OR a friendly slug."""
    skill = get_skill(ref)
    if skill is not None:
        return skill

    from skills.platform import PLATFORM_OWNER_UID

    for owner in (caller_uid, PLATFORM_OWNER_UID):
        if not owner:
            continue
        try:
            found = find_by_slug(owner, ref)
        except Exception as exc:
            logger.warning("slug resolution failed for %r in %s: %s", ref, owner, exc)
            continue
        if found is not None:
            logger.info("skill ref %r resolved by slug in %s -> %s", ref, owner, found.skill_id)
            return found
    return None


def find_jobs(owner_id: str) -> list[SkillConfig]:
    """All skills in ``owner_id``'s namespace tagged as jobs (metadata.job=True)."""
    docs = fs.query_documents(COLLECTION, filters=[("ownerId", "==", owner_id)])
    jobs: list[SkillConfig] = []
    for cfg in _configs_from_docs(docs):
        if cfg.skill_metadata.job:
            _cache_set(cfg.skill_id, cfg)
            jobs.append(cfg)
    return jobs


def update_skill(skill_id: str, updates: dict[str, Any]) -> SkillConfig | None:
    """Update specific fields on a skill. Returns updated config or None if not found."""
    existing = get_skill(skill_id)
    if existing is None:
        return None

    updates["updatedAt"] = time.time()
    merged = {**_to_firestore(existing), **updates}
    SkillConfig.model_validate(merged)

    fs.update_document(COLLECTION, skill_id, updates)
    _cache_invalidate(skill_id)

    data = fs.get_document(COLLECTION, skill_id)
    if data is None:
        return None
    config = _from_firestore(data)
    _cache_set(skill_id, config)
    return config


def delete_skill(skill_id: str) -> bool:
    """Delete a skill. Returns True if it existed."""
    existing = get_skill(skill_id)
    if existing is None:
        return False

    fs.delete_document(COLLECTION, skill_id)
    _cache_invalidate(skill_id)
    return True


def list_skills(
    owner_id: str | None = None,
    tag: str | None = None,
    access_type: str | None = None,
    limit: int = 50,
) -> list[SkillConfig]:
    """List skills with optional filters."""
    filters: list[tuple[str, str, Any]] = []

    if owner_id:
        filters.append(("ownerId", "==", owner_id))
    if tag:
        filters.append(("tags", "array_contains", tag))
    if access_type:
        filters.append(("accessControl.type", "==", access_type))

    docs = fs.query_documents(
        COLLECTION,
        filters=filters if filters else None,
        order_by="updatedAt",
        order_direction="DESCENDING",
        limit=limit,
    )
    return _configs_from_docs(docs)


def list_marketplace(limit: int = 50) -> list[SkillConfig]:
    """List public skills for the marketplace, ordered by usage."""
    docs = fs.query_documents(
        COLLECTION,
        filters=[("accessControl.type", "==", "public")],
        order_by="usageCount",
        order_direction="DESCENDING",
        limit=limit,
    )
    return [c for c in _configs_from_docs(docs) if SYSTEM_TAG not in c.tags]


def increment_usage(skill_id: str) -> None:
    """Atomically increment a skill's usage count."""
    fs.increment_field(COLLECTION, skill_id, "usageCount")
    _cache_invalidate(skill_id)
