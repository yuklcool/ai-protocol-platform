"""Lazy Skill instructions inside a single Root Agent, without spawning agents."""

from __future__ import annotations

from google.adk.tools import FunctionTool, ToolContext

from agents.root_runtime import RootCapabilityDenied, _configured_ref, effective_root_config, resolve_root_capability
from auth import User
from auth.access_context import AccessContext
from config.platform_config import get_platform_config


def root_capability_tool(user: User, access: AccessContext) -> tuple[FunctionTool, str]:
    config = effective_root_config(get_platform_config().agent, access.tenant_id)
    catalog: list[str] = []
    for ref in config.skills:
        skill = _configured_ref(config, ref, user, access)
        if skill is not None:
            catalog.append(f"- {skill.skill_id}: {skill.display_name or skill.name} — {skill.description[:500]}")

    async def load_skill(skill_ref: str, tool_context: ToolContext) -> dict:
        """Load an authorized Skill's instructions for the current task.

        Skills add instructions and reference material to this same Agent.
        They do not change the model or grant additional tools/MCP access.
        Call again when a task needs another capability from the catalog.
        """
        policy = effective_root_config(get_platform_config().agent, access.tenant_id)
        try:
            skill = resolve_root_capability(policy, user, access, skill_ref)
        except RootCapabilityDenied:
            return {"error": "This capability is not available."}
        if skill.skill_id == "root-agent":
            return {"error": "Choose a Skill from the capability catalog."}
        loaded = list(tool_context.state.get("root_loaded_skills") or [])
        if skill.skill_id not in loaded:
            loaded.append(skill.skill_id)
        tool_context.state["root_loaded_skills"] = loaded
        return {
            "skillId": skill.skill_id,
            "instructions": skill.instructions,
            "references": skill.references,
            "assets": skill.assets,
        }

    instruction = (
        "You are the single Root Agent. Skills are capabilities, not separate agents. "
        "Use load_skill to obtain the instructions for capabilities relevant to the user's task. "
        "You may load several Skills for one task. Only the Root Agent's authorized tools and MCP servers may be used.\n"
        "Available capability catalog:\n" + ("\n".join(catalog) or "No additional Skills are bound.")
    )
    return FunctionTool(load_skill), instruction
