"""Shared Agent policy combined with the caller's personal Skill bindings."""

from fastapi import HTTPException

from auth.access_context import build_access_context
from auth.models import User
from db.models.root_agent import RootAgentConfig
from db.persistence import get_repository
from db.user_profiles import get_user_profile


def refresh_authorization(user: User) -> User:
    """Re-read account status and roles; never accept browser role claims."""
    if user.auth_mode in {"local-jwt", "oidc"}:
        from auth.local_jwt import get_local_user_by_email

        row = get_local_user_by_email(user.email)
        if not row or row.get("disabled") or row.get("uid") != user.uid:
            raise HTTPException(403, "Account authorization is unavailable")
        matches = get_repository().query_documents("auth_users", filters=[("uid", "==", user.uid)], limit=2)
        if len(matches) > 1:
            raise HTTPException(403, "Account identity is ambiguous")
        return user.model_copy(update={"group_tags": frozenset(str(tag) for tag in row.get("groupTags") or [])})
    return user


def authorized_root_config(config: RootAgentConfig, user: User) -> RootAgentConfig:
    from skills.skill_config import get_skill
    from tools.mcp.scope import mcp_config_enabled

    user = refresh_authorization(user)
    access = build_access_context(user)
    profile = get_user_profile(user.uid)
    denied = set(config.permissions.get("deniedSkills") or [])
    skills = []
    for ref in dict.fromkeys([*config.skills, *profile.skills]):
        skill = get_skill(ref)
        # A personal binding cannot expose somebody else's private Skill.
        personal = ref in profile.skills and skill is not None and skill.owner_id == user.uid
        if skill and ref not in denied and skill.skill_id not in denied and access.can_access_skill(skill):
            if ref in config.skills or personal:
                skills.append(ref)
    instructions = config.instructions
    if profile.information.strip():
        instructions += "\n\nPersonal information supplied by the current user:\n" + profile.information.strip()
    return config.model_copy(
        deep=True,
        update={
            "skills": skills,
            "instructions": instructions,
            "mcp_servers": [
                ref
                for ref in config.mcp_servers
                if mcp_config_enabled(get_repository().get_document("mcp_servers", ref))
            ],
            "specialist_agents": [ref for ref in config.specialist_agents if ref in skills],
        },
    )


def mcp_call_allowed(user: User, server_id: str, tool_name: str) -> bool:
    from config.platform_config import get_platform_config

    root = authorized_root_config(get_platform_config().agent, user)
    denied = set(root.permissions.get("deniedTools") or [])
    return server_id in root.mcp_servers and tool_name not in denied and "*" not in denied
