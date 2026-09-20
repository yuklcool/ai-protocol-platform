"""Resolve the single user-facing Root Agent at request time.

The Root Agent is a policy and composition layer, not a God Agent.  A turn
resolves one requested capability, verifies it against the configured ceiling
and the caller's effective access, then composes a temporary SkillConfig for
the existing ADK factory.  No other skill, tool or MCP server is loaded or
built as part of that turn.
"""

from __future__ import annotations

from typing import Any

from auth.access_context import AccessContext
from auth.firebase_auth import User
from db.clients import resolve_default_skill, resolve_enabled_skills
from db.models import SkillConfig
from db.models.root_agent import RootAgentConfig
from skills.skill_config import resolve_skill_ref

ROOT_AGENT_ID = "root-agent"


class RootCapabilityDenied(Exception):
    """Raised when the Root Agent cannot use the requested capability."""


def _permission_values(permissions: dict[str, Any], *names: str) -> set[str]:
    values: set[str] = set()
    for name in names:
        raw = permissions.get(name)
        if isinstance(raw, list | tuple | set):
            values.update(str(item) for item in raw if item)
    return values


def _configured_ref(config: RootAgentConfig, ref: str, user: User, access: AccessContext) -> SkillConfig | None:
    skill = resolve_skill_ref(ref, getattr(user, "uid", None))
    if skill is None:
        return None
    if not access.can_access_skill(skill):
        return None

    enabled = resolve_enabled_skills(user)
    if enabled is not None and not access.is_skill_admin(skill):
        # Tenant narrowing is an additional ceiling, never a grant.  Accept
        # ids as well as slugs because RootAgentConfig stores stable resource
        # references while old tenant records store slugs.
        if skill.skill_id not in enabled and (skill.slug or "") not in enabled:
            return None

    denied = _permission_values(config.permissions, "deniedSkills", "denied_skills")
    if ref in denied or skill.skill_id in denied or (skill.slug or "") in denied:
        return None
    return skill


def resolve_root_capability(
    config: RootAgentConfig,
    user: User,
    access: AccessContext,
    requested_ref: str | None = None,
) -> SkillConfig:
    """Resolve exactly one accessible capability for this turn.

    A configured ``skills`` list is a hard Root Agent ceiling.  Before the
    migration is configured, a supplied capability hint is kept as a narrow
    compatibility bridge; it is still checked by ACL and tenant policy and is
    never expanded into a list of all skills.
    """
    configured = [str(ref) for ref in config.skills if str(ref).strip()]
    requested = (requested_ref or "").strip()
    if requested:
        if configured and requested not in configured:
            raise RootCapabilityDenied("requested capability is outside the Root Agent ceiling")
        skill = _configured_ref(config, requested, user, access)
        if skill is None:
            raise RootCapabilityDenied("requested capability is unavailable")
        return skill

    candidates = configured
    if not candidates:
        default_ref = resolve_default_skill(user)
        candidates = [default_ref] if default_ref else []

    for ref in candidates:
        if ref:
            skill = _configured_ref(config, ref, user, access)
            if skill is not None:
                return skill

    raise RootCapabilityDenied("no accessible Root Agent capability is configured")


def compose_root_skill(skill: SkillConfig, config: RootAgentConfig) -> SkillConfig:
    """Compose Root Agent policy over one capability without mutating storage."""
    permissions = config.permissions or {}
    strict = bool(config.skills or config.tools or config.mcp_servers or permissions.get("failClosed") is True)
    metadata = skill.skill_metadata.model_copy(deep=True)
    tool_configs = dict(metadata.tool_configs or {})

    if strict:
        allowed_tools = set(config.tools)
        metadata.tools = [tool for tool in metadata.tools if tool in allowed_tools]

        # The legacy factory adds artifact/memory defaults outside metadata.tools.
        # Make the Root Agent ceiling apply to those defaults too.
        defaults = dict(tool_configs.get("defaults") or {})
        defaults["artifacts"] = "load_artifacts_tool" in allowed_tools or "retrieve_artifact" in allowed_tools
        defaults["memory"] = "load_memory_tool" in allowed_tools or "preload_memory_tool" in allowed_tools
        tool_configs["defaults"] = defaults

        mcp = dict(tool_configs.get("mcp") or {})
        mcp["servers"] = [server for server in mcp.get("servers", []) if server in set(config.mcp_servers)]
        tool_configs["mcp"] = mcp

    if config.interaction.a2ui_enabled is False:
        a2ui = dict(tool_configs.get("a2ui") or {})
        a2ui["enabled"] = False
        tool_configs["a2ui"] = a2ui

    metadata.tool_configs = tool_configs
    metadata.model = config.model or metadata.model
    root_instructions = (config.instructions or "").strip()
    capability_instructions = (skill.instructions or "").strip()
    instructions = "\n\n".join(part for part in (root_instructions, capability_instructions) if part)

    return skill.model_copy(
        deep=True,
        update={
            "instructions": instructions,
            "skill_metadata": metadata,
        },
    )


__all__ = [
    "ROOT_AGENT_ID",
    "RootCapabilityDenied",
    "compose_root_skill",
    "resolve_root_capability",
]
