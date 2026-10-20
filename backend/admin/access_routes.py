"""使用运行时同一份授权结果预览有效访问。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from admin.accounts_routes import account_view
from admin.scope import Scope
from agents.root_runtime import _configured_ref
from auth.access_context import build_access_context
from auth.capability_access import authorized_root_config, refresh_authorization
from auth.local_jwt import get_local_user_by_email
from auth.models import User
from config.platform_config import get_platform_config

router = APIRouter(prefix="/api/admin/access", tags=["admin-access"])


class AccessCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str


@router.post("/check")
def check_access(body: AccessCheckRequest, scope: Scope) -> dict:
    row = get_local_user_by_email(body.email)
    if row is None:
        raise HTTPException(404, "账号不存在")
    if row.get("disabled"):
        return {"account": account_view(row), "skills": [], "mcpServers": [], "reason": "账号已停用"}
    user = refresh_authorization(
        User(
            uid=row["uid"],
            email=row["email"],
            domain=row.get("domain", ""),
            auth_mode="local-jwt",
        )
    )
    access = build_access_context(user)
    root = authorized_root_config(get_platform_config().agent, user)
    skills = []
    for ref in root.skills:
        skill = _configured_ref(root, ref, user, access)
        if skill:
            skills.append({"id": skill.skill_id, "label": skill.display_name or skill.name})
    return {
        "account": account_view(row),
        "skills": skills,
        "mcpServers": root.mcp_servers,
        "reason": "Agent 公共能力与用户专有 Skill 的合并结果, Skills 受资源 ACL 约束",
    }
