"""Root、租户和权限组交集。所有运行入口读取同一份当前授权。"""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from auth.access_context import build_access_context
from auth.admin_roles import PLATFORM_ADMIN_TAG, TENANT_ADMIN_PREFIX, is_admin_conferring_tag
from auth.models import User
from db.models.root_agent import RootAgentConfig
from db.persistence import get_repository

GROUP_COLLECTION = "permission_groups"


class PermissionGroup(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    id: str = ""
    tenant_id: str = Field(alias="tenantId", min_length=1)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    skills: list[str] = Field(default_factory=list, max_length=200)
    mcp_servers: list[str] = Field(default_factory=list, alias="mcpServers", max_length=100)
    role: Literal["member", "tenant-admin"] = "member"


def user_groups(user: User) -> list[PermissionGroup]:
    groups = []
    for group_id in sorted(user.permission_group_ids):
        raw = get_repository().get_document(GROUP_COLLECTION, group_id)
        if not raw:
            continue
        group = PermissionGroup.model_validate({key: value for key, value in raw.items() if key != "__id"})
        if group.tenant_id == user.tenant_id:
            groups.append(group)
    return groups


def refresh_authorization(user: User) -> User:
    """身份由认证器验证; 成员关系和角色每次从服务端读取, 不缓存到 JWT。"""
    if user.auth_mode in {"local-jwt", "oidc"}:
        from auth.local_jwt import get_local_user_by_email

        row = get_local_user_by_email(user.email)
        if not row or row.get("disabled") or row.get("uid") != user.uid or row.get("tenantId") != user.tenant_id:
            raise HTTPException(403, "Account authorization is unavailable")
        tags = frozenset(str(tag) for tag in (row.get("groupTags") or []))
        user = user.model_copy(
            update={
                "group_tags": tags,
                "permission_group_ids": frozenset(str(value) for value in (row.get("permissionGroupIds") or [])),
            }
        )
    tags = {tag for tag in user.group_tags if not is_admin_conferring_tag(tag)}
    # 平台超级管理员由受保护的身份记录提供, 权限组不能创建此角色。
    if PLATFORM_ADMIN_TAG in user.group_tags:
        tags.add(PLATFORM_ADMIN_TAG)
    from db.tenants import get_tenant

    tenant = get_tenant(user.tenant_id)
    if tenant is not None and tenant.disabled and PLATFORM_ADMIN_TAG not in tags:
        raise HTTPException(403, "Tenant is disabled")
    groups = user_groups(user)
    tags.update(group.id for group in groups if not is_admin_conferring_tag(group.id))
    if any(group.role == "tenant-admin" for group in groups):
        tags.add(f"{TENANT_ADMIN_PREFIX}{user.tenant_id}")
    return user.model_copy(update={"group_tags": frozenset(tags)})


def authorized_root_config(config: RootAgentConfig, user: User) -> RootAgentConfig:
    """先应用租户 Root 替换, 再与租户白名单、权限组并集求交集。"""
    from agents.root_runtime import effective_root_config
    from db.tenants import get_tenant
    from tools.mcp.tenant_scope import mcp_config_visible_to_tenant

    user = refresh_authorization(user)
    root = effective_root_config(config, user.tenant_id)
    tenant = get_tenant(user.tenant_id)
    if tenant is None or tenant.disabled:
        return root.model_copy(
            update={
                "skills": [],
                "tools": [],
                "mcp_servers": [],
                "knowledge": [],
                "specialist_agents": [],
                "tenant_overrides": {},
            }
        )
    groups = user_groups(user)
    group_skills = {ref for group in groups for ref in group.skills}
    group_mcp = {ref for group in groups for ref in group.mcp_servers}
    if build_access_context(user).is_platform_admin:
        group_skills = set(root.skills)
        group_mcp = set(root.mcp_servers)
    allowed_skills = set(tenant.enabled_skills or []) & group_skills
    allowed_mcp = set(tenant.enabled_mcp_servers) & group_mcp
    repository = get_repository()
    from skills.skill_config import get_skill

    access = build_access_context(user)
    denied_skills = set(root.permissions.get("deniedSkills") or [])
    skills = []
    for ref in root.skills:
        if ref not in allowed_skills or ref in denied_skills:
            continue
        skill = get_skill(ref)
        if skill is not None and access.can_access_skill(skill):
            skills.append(ref)
    return root.model_copy(
        deep=True,
        update={
            "skills": skills,
            "mcp_servers": [
                ref
                for ref in root.mcp_servers
                if ref in allowed_mcp
                and mcp_config_visible_to_tenant(
                    repository.get_document("mcp_servers", ref),
                    user.tenant_id,
                )
            ],
            "specialist_agents": [ref for ref in root.specialist_agents if ref in skills],
            "tenant_overrides": {},
        },
    )


def mcp_call_allowed(user: User, server_id: str, tool_name: str) -> bool:
    from config.platform_config import get_platform_config

    root = authorized_root_config(get_platform_config().agent, user)
    denied = set(root.permissions.get("deniedTools") or [])
    return server_id in root.mcp_servers and tool_name not in denied and "*" not in denied
