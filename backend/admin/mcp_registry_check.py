"""MCP-registry consistency check — the issue #14 seed-drift safeguard.

Why this exists: strict MCP resolution hard-fails a skill at agent-build time
when its SKILL.md declares a server the persisted ``mcp_servers`` registry
cannot satisfy. Runtime registry access is backend-neutral; this verifier must
use the same persistence boundary so PostgreSQL self-hosts are checked against
their real registry instead of Firestore.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from db.persistence import get_document

logger = logging.getLogger(__name__)

COLLECTION = "mcp_servers"

KNOWN_SEEDABLE_SERVER_IDS = {"ext-apps-map", "toolbox", "toolbox-bq", "maps-grounding-lite"}
LOOPBACK_BY_DESIGN = {"toolbox", "toolbox-bq"}


def declared_servers_by_skill(templates_root: Path) -> dict[str, list[str]]:
    """Map skill template name to MCP server ids declared by its SKILL.md."""
    from admin.platform_seed import _parse_template

    declared: dict[str, list[str]] = {}
    if not templates_root.is_dir():
        return declared
    for child in sorted(templates_root.iterdir()):
        skill_md = child / "SKILL.md"
        if not (child.is_dir() and skill_md.exists()):
            continue
        try:
            parsed = _parse_template(skill_md)
        except Exception:
            continue
        tool_configs = (parsed.get("metadata") or {}).get("toolConfigs") or {}
        servers = (tool_configs.get("mcp") or {}).get("servers") or []
        if servers:
            declared[parsed["name"]] = [str(s) for s in servers]
    return declared


def verify_mcp_registry(templates_root: Path, *, deployed: bool | None = None) -> dict[str, Any]:
    """Check every template-declared MCP server against configured persistence."""
    if deployed is None:
        deployed = bool(os.environ.get("K_SERVICE"))

    declared = declared_servers_by_skill(templates_root)
    missing: set[str] = set()
    warnings: set[str] = set()
    cache: dict[str, dict[str, Any] | None] = {}

    for skill, server_ids in declared.items():
        for sid in server_ids:
            if sid not in cache:
                try:
                    cache[sid] = get_document(COLLECTION, sid)
                except Exception as exc:
                    logger.warning("mcp_registry_check: read failed for %s: %s", sid, exc)
                    warnings.add(f"{sid}: registry read failed ({exc}) — cannot verify")
                    cache[sid] = {}
                    continue
            doc = cache[sid]
            if doc == {}:
                continue
            if not doc or not doc.get("url"):
                missing.add(f"{skill} -> {sid}")
                continue
            url = str(doc["url"])
            if deployed and sid not in LOOPBACK_BY_DESIGN and ("127.0.0.1" in url or "localhost" in url):
                warnings.add(
                    f"{skill} -> {sid}: url={url} is loopback but this env is deployed — "
                    "the tool will silently resolve to no tools"
                )

    return {
        "ok": not missing,
        "mcp_missing": sorted(missing),
        "mcp_warnings": sorted(warnings),
        "declared": declared,
    }
