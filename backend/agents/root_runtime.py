"""Resolve the single user-facing Root Agent at request time.

The Root Agent is a policy and composition layer, not a God Agent.  A turn
resolves one requested capability, verifies it against the configured ceiling
and the caller's effective access, then composes a temporary SkillConfig for
the existing ADK factory.  No other skill, tool or MCP server is loaded or
built as part of that turn.
"""

from __future__ import annotations

import os
from typing import Any

from auth.access_context import AccessContext
from auth.models import User
from db.models import DelegationConfig, FallbackConfig, SkillConfig, SkillMetadata, SkillPersona, SkillVoiceConfig
from db.models.root_agent import RootAgentConfig
from skills import platform
from skills.skill_config import resolve_skill_ref

ROOT_AGENT_ID = "root-agent"


def root_agent_skill(config: RootAgentConfig) -> SkillConfig:
    """Storage-independent identity for the one user-facing Agent."""
    return SkillConfig(
        name=ROOT_AGENT_ID,
        skillId=ROOT_AGENT_ID,
        displayName=config.display_name,
        description=config.description,
        ownerId=platform.PLATFORM_OWNER_UID,
        accessControl={"type": "public"},
        skillMetadata=SkillMetadata(model=config.model),
    )


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
    from auth.access_context import build_access_context
    from auth.capability_access import refresh_authorization

    user = refresh_authorization(user)
    access = build_access_context(user)
    skill = resolve_skill_ref(ref, getattr(user, "uid", None))
    if skill is None:
        return None
    if not access.can_access_skill(skill):
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
    """只加载当前授权列表中的 Skill; 空列表禁止所有额外能力。"""
    requested = (requested_ref or "").strip()
    if not requested or requested == ROOT_AGENT_ID:
        return root_agent_skill(config)
    if not config.skills:
        raise RootCapabilityDenied("requested capability is outside the Root Agent ceiling")
    skill = _configured_ref(config, requested, user, access)
    if skill is None or skill.skill_id not in config.skills:
        raise RootCapabilityDenied("requested capability is unavailable")
    return skill


def compose_root_skill(skill: SkillConfig, config: RootAgentConfig) -> SkillConfig:
    """Compose Root Agent policy over one capability without mutating storage."""
    metadata = skill.skill_metadata.model_copy(deep=True)
    tool_configs = dict(metadata.tool_configs or {})
    tool_configs["root_agent"] = {"enabled": True, "budget_enabled": config.budget_enabled}
    if config.budget_enabled:
        # A capability cannot exempt itself or choose another user bucket.
        tool_configs["budget"] = {"identity_key": "uid", "missing_identity_policy": "block"}

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

    # MCP 连接只来自当前 Root 配置;Skill 内容不能附带连接或写入授权。
    tool_configs["mcp"] = {"servers": list(dict.fromkeys(config.mcp_servers))}

    interaction = config.interaction
    metadata.enable_confirmation = interaction.a2ui_enabled
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
    tool_configs["knowledge"] = {"sources": list(config.knowledge)}

    metadata.tool_configs = tool_configs
    metadata.model = config.model or metadata.model
    root_instructions = (config.instructions or "").strip()
    capability_instructions = (skill.instructions or "").strip()
    instructions = "\n\n".join(part for part in (root_instructions, capability_instructions) if part)
    if "update_task_plan" in metadata.tools:
        from tools.task_plan import PLAN_INSTRUCTIONS

        instructions += "\n\n" + PLAN_INSTRUCTIONS
    persona = skill.persona.model_copy(deep=True) if skill.persona else SkillPersona()
    voice = persona.voice.model_copy(deep=True) if persona.voice else SkillVoiceConfig()
    voice.enabled = interaction.voice_enabled
    voice.tts_provider = os.environ.get("TTS_PROVIDER", "browser")
    voice.language = os.environ.get("TTS_LANGUAGE", "zh-CN")
    persona.voice = voice

    return skill.model_copy(
        deep=True,
        update={
            "instructions": instructions,
            "initial_message": config.interaction.welcome_message or skill.initial_message,
            "skill_metadata": metadata,
            "display_name": config.display_name,
            "persona": persona,
        },
    )


__all__ = [
    "ROOT_AGENT_ID",
    "RootCapabilityDenied",
    "compose_root_skill",
    "resolve_root_capability",
]
