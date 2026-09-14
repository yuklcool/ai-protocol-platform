"""Seed the default platform-owned skills into configured persistence.

The seeder is intentionally backend-neutral. Skill documents and the wildcard
Tool permission are persisted through the repository facade selected by
``DATA_BACKEND`` while preserving the existing seed/refresh/purge behaviour.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from config.local_mode import is_local_mode
from db import persistence as fs
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID
from skills.slugify import slugify, unique_slug

logger = logging.getLogger(__name__)

PLATFORM_OWNER_EMAIL = os.environ.get("PLATFORM_OWNER_EMAIL", "platform@yourcompany.com")
DEFAULT_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "skills" / "templates"

# Demo skills shipped with the template. Public-template forks can opt out by
# setting _INCLUDE_DEMO_SKILLS=false while platform deployments keep the
# backwards-compatible default of including them.
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
    """Parse YAML frontmatter + markdown body from a SKILL.md template."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter in {skill_md}")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"missing frontmatter close fence in {skill_md}")

    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter in {skill_md}: {exc}") from exc

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
                logger.info(
                    "platform_seed: [dry-run] would purge stale skill %r (previous_owner=%s)",
                    cfg.name,
                    uid,
                )
                purged += 1
                continue
            if skill_config.delete_skill(cfg.skill_id):
                logger.info(
                    "platform_seed: purged stale skill %r (previous_owner=%s)",
                    cfg.name,
                    uid,
                )
                purged += 1
    return purged


def _ensure_tool_permissions_wildcard(dry_run: bool = False) -> bool:
    """Create the default wildcard Tool permission through the repository facade."""
    existing = fs.get_document("tool_permissions", "*")
    if existing is not None:
        return False
    if dry_run:
        logger.info("platform_seed: [dry-run] would seed tool_permissions wildcard allow-all rule")
        return True

    fs.set_document(
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
    """Resolve the platform owner and fail loudly outside LOCAL_MODE."""
    email = os.environ.get("PLATFORM_OWNER_EMAIL", "")
    if email:
        return email
    if is_local_mode():
        return "platform@localhost"
    raise RuntimeError(
        "PLATFORM_OWNER_EMAIL env var is required in non-LOCAL_MODE. "
        "Set it to the platform admin email for this deployment "
        "(e.g. platform@yourdomain.com). "
        "Forks: add it to your Cloud Build substitutions as _PLATFORM_OWNER_EMAIL."
    )


def seed(templates_root: Path | None = None, dry_run: bool = False) -> SeedSummary:
    """Seed platform skills from disk templates while preserving legacy semantics.

    Existing template-managed skills are refreshed, durable
    ``managed_by='firestore'`` skills are preserved, previous-owner skills can
    be purged, and dry-run performs no writes.
    """
    owner_email = _resolve_owner_email()
    root = templates_root or DEFAULT_TEMPLATES_ROOT
    summary = SeedSummary()
    summary.tool_permissions_wildcard_seeded = _ensure_tool_permissions_wildcard(
        dry_run=dry_run
    )

    summary.purged = _purge_stale_owner_skills(
        _previous_owner_uids(), dry_run=dry_run
    )
    existing_by_name = _existing_platform_skill_by_name()
    include_demos = _include_demo_skills()

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        if not include_demos and child.name in DEMO_SKILL_NAMES:
            logger.info(
                "platform_seed: skipping demo skill %r (_INCLUDE_DEMO_SKILLS != 'true')",
                child.name,
            )
            summary.skipped += 1
            continue

        try:
            parsed = _parse_template(skill_md)
        except Exception as exc:
            logger.warning("platform_seed: failed to parse %s: %s", skill_md, exc)
            summary.failed.append(child.name)
            continue

        if parsed["name"] in existing_by_name:
            existing_cfg = existing_by_name[parsed["name"]]
            if getattr(existing_cfg, "managed_by", None) == "firestore":
                summary.preserved += 1
                continue

            refresh_payload: dict[str, Any] = {
                "description": parsed["description"],
                "instructions": parsed["instructions"],
                "skillMetadata": parsed["metadata"],
                "managedBy": "template",
            }
            if parsed.get("welcome") is not None:
                refresh_payload["welcome"] = parsed["welcome"]
            if parsed.get("shell") is not None:
                refresh_payload["shell"] = parsed["shell"]
            if parsed.get("access_control") is not None:
                refresh_payload["accessControl"] = parsed["access_control"]
            if parsed.get("initial_message"):
                refresh_payload["initialMessage"] = parsed["initial_message"]
            if parsed.get("display_name"):
                refresh_payload["displayName"] = parsed["display_name"]
            if parsed.get("tags"):
                refresh_payload["tags"] = parsed["tags"]
            if parsed.get("avatar"):
                refresh_payload["avatar"] = parsed["avatar"]
            if not getattr(existing_cfg, "slug", None):
                refresh_payload["slug"] = unique_slug(
                    PLATFORM_OWNER_UID, slugify(parsed["name"])
                )

            try:
                if not dry_run:
                    skill_config.update_skill(existing_cfg.skill_id, refresh_payload)
                summary.refreshed += 1
            except Exception as exc:
                logger.warning(
                    "platform_seed: failed to refresh %s: %s",
                    parsed["name"],
                    exc,
                )
                summary.failed.append(parsed["name"])
            continue

        try:
            slug = unique_slug(PLATFORM_OWNER_UID, slugify(parsed["name"]))
            create_kwargs: dict[str, Any] = {
                "name": parsed["name"],
                "description": parsed["description"],
                "instructions": parsed["instructions"],
                "owner_id": PLATFORM_OWNER_UID,
                "owner_email": owner_email,
                "accessControl": parsed.get("access_control") or {"type": "public"},
                "skillMetadata": parsed["metadata"],
                "slug": slug,
                "managedBy": "template",
            }
            if parsed.get("welcome") is not None:
                create_kwargs["welcome"] = parsed["welcome"]
            if parsed.get("shell") is not None:
                create_kwargs["shell"] = parsed["shell"]
            if parsed.get("initial_message"):
                create_kwargs["initialMessage"] = parsed["initial_message"]
            if parsed.get("display_name"):
                create_kwargs["displayName"] = parsed["display_name"]
            if parsed.get("tags"):
                create_kwargs["tags"] = parsed["tags"]
            if parsed.get("avatar"):
                create_kwargs["avatar"] = parsed["avatar"]
            if not dry_run:
                skill_config.create_skill(**create_kwargs)
            summary.created += 1
        except Exception as exc:
            logger.warning("platform_seed: failed to create %s: %s", parsed["name"], exc)
            summary.failed.append(parsed["name"])

    try:
        from admin.mcp_registry_check import verify_mcp_registry

        check = verify_mcp_registry(root)
        summary.mcp_missing = check["mcp_missing"]
        summary.mcp_warnings = check["mcp_warnings"]
        if summary.mcp_missing:
            logger.error(
                "platform_seed: mcp_servers registry cannot satisfy declared servers "
                "(these skills would hard-500 at agent build): %s",
                summary.mcp_missing,
            )
        for warning in summary.mcp_warnings:
            logger.warning("platform_seed: mcp registry: %s", warning)
    except Exception as exc:
        logger.warning("platform_seed: mcp registry check crashed: %s", exc)
        summary.mcp_warnings = [
            f"mcp-registry check crashed (verification skipped): {exc}"
        ]

    return summary


def seed_platform_skills(
    templates_root: Path = DEFAULT_TEMPLATES_ROOT,
    *,
    dry_run: bool = False,
) -> SeedSummary:
    """Compatibility entry point for callers introduced during persistence work."""
    return seed(templates_root=templates_root, dry_run=dry_run)


__all__ = [
    "DEFAULT_TEMPLATES_ROOT",
    "DEMO_SKILL_NAMES",
    "PLATFORM_OWNER_EMAIL",
    "SeedSummary",
    "_parse_template",
    "seed",
    "seed_platform_skills",
]
