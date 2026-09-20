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
from db.models import DelegationConfig, FallbackConfig, SkillConfig
from db.models.root_agent import RootAgentConfig
from skills.skill_config import resolve_skill_ref

ROOT_AGENT_ID = "root-agent"


class RootCapabilityDenied(Exception):
    """Raised when the Root Agent cannot use the requested capability."""


def effective_root_config(config: RootAgentConfig, tenant_id: str | None) -> RootAgentConfig:
    """Apply the tenant policy overlay without widening the global policy.

    A tenant override is an explicit replacement for list-valued bindings, so
    tenant-private Skills do not need to be stored in the platform-wide
    ``skills`` list. Fields omitted by the override inherit the global value.
    """
    tenant = (tenant_id or "").strip()
    override = config.tenant_overrides.get(tenant) if tenant else None
    if override is None:
        return config

    updates: dict[str, Any] = {}
    for field in (
        "model",
        "instructions",
        "skills",
        "tools",
        "mcp_servers",
        "knowledge",
        "interaction",
        "permissions",
        "specialist_agents",
    ):
        value = getattr(override, field)
        if value is not None:
            updates[field] = value
    return config.model_copy(deep=True, update=updates)


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
    fail_closed = (config.permissions or {}).get("failClosed") is True
    requested = (requested_ref or "").strip()
    if requested:
        # A fail-closed Root Agent cannot be widened by a client-supplied
        # capability hint when the admin has not configured an allow-list.
        # Keep the legacy compatibility bridge only when it is explicitly
        # opted into by leaving failClosed false.
        if fail_closed and not configured:
            raise RootCapabilityDenied("Root Agent capability ceiling is empty")
        if configured and requested not in configured:
            requested_skill = resolve_skill_ref(requested, getattr(user, "uid", None))
            if requested_skill is None or (
                requested_skill.skill_id not in configured and (requested_skill.slug or "") not in configured
            ):
                raise RootCapabilityDenied("requested capability is outside the Root Agent ceiling")
        skill = _configured_ref(config, requested, user, access)
        if skill is None:
            raise RootCapabilityDenied("requested capability is unavailable")
        return skill

    candidates = configured
    if not candidates:
        if fail_closed:
            raise RootCapabilityDenied("no Root Agent capability is configured")
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

    # Skill-level model strategy and delegation are not Root Agent policy.
    # Clear them before composing so a capability cannot smuggle in a second
    # model, fallback egress path, or specialist graph. Specialists must be
    # explicitly bound at the Root Agent level.
    metadata.thinking_model = None
    metadata.fallback = FallbackConfig()
    metadata.sub_skills = []
    metadata.delegation = DelegationConfig(
        enabled=bool(config.specialist_agents),
        allow=list(config.specialist_agents),
        maxDepth=1,
    )

    if strict:
        allowed_tools = set(config.tools)
        # Root-level bindings are the authoritative capability set. This is
        # intentionally not an intersection with the Skill's old list: a
        # Root Agent tool may be bound once at the Agent level even when a
        # legacy Skill never declared it.
        metadata.tools = list(dict.fromkeys(config.tools))

        # The legacy factory adds artifact/memory defaults outside metadata.tools.
        # Make the Root Agent ceiling apply to those defaults too.
        defaults = dict(tool_configs.get("defaults") or {})
        defaults["artifacts"] = "load_artifacts_tool" in allowed_tools or "retrieve_artifact" in allowed_tools
        defaults["memory"] = "load_memory_tool" in allowed_tools or "preload_memory_tool" in allowed_tools
        tool_configs["defaults"] = defaults

        mcp = dict(tool_configs.get("mcp") or {})
        # MCP servers are Root Agent bindings, not Skill-owned connections.
        # The registry and tenant visibility checks still apply when the ADK
        # toolset is resolved.
        mcp["servers"] = list(dict.fromkeys(config.mcp_servers))
        tool_configs["mcp"] = mcp

    interaction = config.interaction
    a2ui = dict(tool_configs.get("a2ui") or {})
    a2ui.update(
        {
            "enabled": interaction.a2ui_enabled,
            "default_surface": interaction.default_surface,
            "default_update_mode": interaction.default_update_mode,
            "allow_surface_context_writes": interaction.allow_surface_context_writes,
            "allow_action_triggered_runs": interaction.allow_action_triggered_runs,
        }
    )
    tool_configs["a2ui"] = a2ui
    if config.knowledge:
        tool_configs["knowledge"] = {"sources": list(config.knowledge)}

    metadata.tool_configs = tool_configs
    metadata.model = config.model or metadata.model
    root_instructions = (config.instructions or "").strip()
    capability_instructions = (skill.instructions or "").strip()
    instructions = "\n\n".join(part for part in (root_instructions, capability_instructions) if part)

    return skill.model_copy(
        deep=True,
        update={
            "instructions": instructions,
            "initial_message": config.interaction.welcome_message or skill.initial_message,
            "skill_metadata": metadata,
        },
    )


__all__ = [
    "ROOT_AGENT_ID",
    "RootCapabilityDenied",
    "compose_root_skill",
    "effective_root_config",
    "resolve_root_capability",
]
