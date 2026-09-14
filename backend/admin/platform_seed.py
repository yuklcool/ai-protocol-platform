"""Seed the five default platform-owned skills into configured persistence.

Called by POST /api/admin/seed-platform-skills, which is hit once per
deploy by the Cloud Build seed step. Idempotent: any template whose
`name` already exists as a platform-owned skill is skipped, so repeat
runs are safe (and the expected steady state).

Template layout (one directory per skill):
    backend/skills/templates/<name>/SKILL.md    # YAML frontmatter + markdown body

The frontmatter supplies name/description/metadata; the body is the
agent instruction. Platform-owned skills are always created with
owner_id=PLATFORM_OWNER_UID and accessControl={type: public}.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from config.local_mode import is_local_mode
from db.persistence import get_document, set_document
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID
from skills.slugify import slugify, unique_slug

logger = logging.getLogger(__name__)

# Email recorded as the owner of platform-seeded skills.
# Resolved lazily by _resolve_owner_email() so module import never raises —
# the validation fires at seed() call time where the error message is actionable.
PLATFORM_OWNER_EMAIL = os.environ.get("PLATFORM_OWNER_EMAIL", "platform@yourcompany.com")
DEFAULT_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "skills" / "templates"

DEMO_SKILL_NAMES: frozenset[str] = frozenset(
    {
        "code-assistant",
        "data-extractor",
        "document-analyst",
        "general-assistant",
        "knowledge-search",
        "maps-assistant",
        "web-researcher",
        "workspace-demo",
        "workspace-demo-interactive",
    }
)


def _include_demo_skills() -> bool:
    raw = os.environ.get("_INCLUDE_DEMO_SKILLS", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class SeedSummary:
    created: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    tool_permissions_wildcard_seeded: bool = False
    refreshed: int = 0
    purged: int = 0
    preserved: int = 0
    mcp_missing: list[str] = field(default_factory=list)
    mcp_warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "tool_permissions_wildcard_seeded": self.tool_permissions_wildcard_seeded,
            "refreshed": self.refreshed,
            "purged": self.purged,
            "preserved": self.preserved,
            "mcp_missing": self.mcp_missing,
            "mcp_warnings": self.mcp_warnings,
        }


def _parse_template(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text()
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter in {skill_md}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"missing frontmatter close fence in {skill_md}")
    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML frontmatter in {skill_md}: {e}") from e
    if "name" not in front:
        raise ValueError(f"frontmatter missing 'name' in {skill_md}")
    return {
        "name": front["name"],
        "description": (front.get("description") or "").strip(),
        "instructions": parts[2].strip(),
        "metadata": front.get("metadata") or {},
        "welcome": front.get("welcome"),
        "shell": front.get("shell"),
        "access_control": front.get("access_control") or front.get("accessControl"),
        "initial_message": front.get("initial_message") or front.get("initialMessage") or "",
        "display_name": front.get("display_name") or front.get("displayName") or "",
        "tags": front.get("tags") or [],
        "avatar": front.get("avatar") or "",
    }


def _existing_platform_skill_names() -> set[str]:
    configs = skill_config.list_skills(owner_id=PLATFORM_OWNER_UID, limit=200)
    return {c.name for c in configs}


def _existing_platform_skill_by_name() -> dict[str, Any]:
    configs = skill_config.list_skills(owner_id=PLATFORM_OWNER_UID, limit=200)
    return {c.name: c for c in configs}


def _previous_owner_uids() -> list[str]:
    raw = os.environ.get("PLATFORM_PREVIOUS_OWNER_UIDS", "").strip()
    if not raw:
        return []
    return [uid.strip() for uid in raw.split(",") if uid.strip()]


def _purge_stale_owner_skills(previous_uids: list[str], dry_run: bool = False) -> int:
    if not previous_uids:
        return 0
    purged = 0
    for uid in previous_uids:
        configs = skill_config.list_skills(owner_id=uid, limit=200)
        for cfg in configs:
            if dry_run:
                logger.info("platform_seed: [dry-run] would purge stale skill %r (previous_owner=%s)", cfg.name, uid)
                purged += 1
                continue
            if skill_config.delete_skill(cfg.skill_id):
                logger.info("platform_seed: purged stale skill %r (previous_owner=%s)", cfg.name, uid)
                purged += 1
    return purged


def _ensure_tool_permissions_wildcard(dry_run: bool = False) -> bool:
    """Idempotent: write a wildcard allow-all rule if none exists."""
    existing = get_document("tool_permissions", "*")
    if existing is not None:
        return False
    if dry_run:
        logger.info("platform_seed: [dry-run] would seed tool_permissions wildcard allow-all rule")
        return True
    set_document(
        "tool_permissions",
        "*",
        {
            "type": "wildcard",
            "tools": ["*"],
            "denied": [],
            "created_by": "platform_seed",
        },
    )
    logger.info("platform_seed: seeded tool_permissions wildcard allow-all rule")
    return True


def _resolve_owner_email() -> str:
    email = os.environ.get("PLATFORM_OWNER_EMAIL", "")
    if email:
        return email
    if is_local_mode():
        return PLATFORM_OWNER_EMAIL
    raise RuntimeError(
        "PLATFORM_OWNER_EMAIL must be set before seeding platform skills outside LOCAL_MODE"
    )


def seed_platform_skills(
    templates_root: Path = DEFAULT_TEMPLATES_ROOT,
    *,
    dry_run: bool = False,
) -> SeedSummary:
    """Seed/update platform-owned skill templates and required defaults."""
    summary = SeedSummary()
    owner_email = _resolve_owner_email()

    summary.tool_permissions_wildcard_seeded = _ensure_tool_permissions_wildcard(dry_run=dry_run)

    previous_uids = _previous_owner_uids()
    summary.purged = _purge_stale_owner_skills(previous_uids, dry_run=dry_run)

    existing = _existing_platform_skill_by_name()
    if not templates_root.is_dir():
        logger.warning("platform_seed: templates root %s does not exist", templates_root)
        return summary

    include_demos = _include_demo_skills()
    for skill_dir in sorted(templates_root.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not (skill_dir.is_dir() and skill_md.exists()):
            continue
        try:
            template = _parse_template(skill_md)
        except Exception as exc:
            summary.failed.append(f"{skill_dir.name}: {exc}")
            continue

        name = template["name"]
        if not include_demos and name in DEMO_SKILL_NAMES:
            summary.skipped += 1
            continue

        current = existing.get(name)
        if current is not None:
            if getattr(current, "managed_by", None) == "firestore":
                summary.preserved += 1
                continue
            if dry_run:
                summary.refreshed += 1
                continue
            try:
                skill_config.update_skill(
                    current.skill_id,
                    name=name,
                    description=template["description"],
                    instructions=template["instructions"],
                    metadata=template["metadata"],
                    welcome=template["welcome"],
                    shell=template["shell"],
                    access_control=template["access_control"] or {"type": "public"},
                    initial_message=template["initial_message"],
                    display_name=template["display_name"],
                    tags=template["tags"],
                    avatar=template["avatar"],
                )
                summary.refreshed += 1
            except Exception as exc:
                summary.failed.append(f"{name}: {exc}")
            continue

        if dry_run:
            summary.created += 1
            continue

        try:
            existing_slugs = {c.slug for c in skill_config.list_skills(limit=500) if c.slug}
            slug = unique_slug(slugify(name), existing_slugs)
            skill_config.create_skill(
                owner_id=PLATFORM_OWNER_UID,
                owner_email=owner_email,
                name=name,
                description=template["description"],
                instructions=template["instructions"],
                metadata=template["metadata"],
                welcome=template["welcome"],
                shell=template["shell"],
                access_control=template["access_control"] or {"type": "public"},
                initial_message=template["initial_message"],
                display_name=template["display_name"],
                tags=template["tags"],
                avatar=template["avatar"],
                slug=slug,
                managed_by="template",
            )
            summary.created += 1
        except Exception as exc:
            summary.failed.append(f"{name}: {exc}")

    try:
        from admin.mcp_registry_check import verify_mcp_registry

        mcp_check = verify_mcp_registry(templates_root)
        summary.mcp_missing = mcp_check["mcp_missing"]
        summary.mcp_warnings = mcp_check["mcp_warnings"]
    except Exception as exc:
        logger.warning("platform_seed: MCP registry verification failed: %s", exc)
        summary.mcp_warnings.append(f"registry verification failed: {exc}")

    return summary


__all__ = [
    "DEFAULT_TEMPLATES_ROOT",
    "DEMO_SKILL_NAMES",
    "PLATFORM_OWNER_EMAIL",
    "SeedSummary",
    "_parse_template",
    "seed_platform_skills",
]
