"""按租户管理权限组, 直接选择 Root 和租户允许的 Skills / MCP。"""

import uuid

from fastapi import APIRouter, HTTPException

from admin.audit import record_admin_action
from admin.scope import Scope
from agents.root_runtime import effective_root_config
from auth.capability_access import GROUP_COLLECTION, PermissionGroup
from config.platform_config import get_platform_config
from db.persistence import get_repository
from db.tenants import get_tenant
from skills.skill_config import get_skill
from tools.mcp.tenant_scope import mcp_config_visible_to_tenant

router = APIRouter(prefix="/api/admin/groups", tags=["admin-groups"])


def _tenant(tenant_id: str, scope: Scope):
    scope.assert_may_tenant(tenant_id)
    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(404, "租户不存在")
    return tenant


@router.get("/resources")
def resources(tenant_id: str, scope: Scope) -> dict:
    tenant = _tenant(tenant_id, scope)
    root = effective_root_config(get_platform_config().agent, tenant_id)
    skills = []
    for ref in root.skills:
        skill = get_skill(ref)
        if (
            skill
            and ref in (tenant.enabled_skills or [])
            and (skill.tenant_id == tenant_id or (not skill.tenant_id and skill.owner_id == "aitana-platform"))
        ):
            skills.append({"id": ref, "label": skill.display_name or skill.name})
    servers = []
    for ref in root.mcp_servers:
        server = get_repository().get_document("mcp_servers", ref)
        if ref in tenant.enabled_mcp_servers and mcp_config_visible_to_tenant(server, tenant_id):
            servers.append({"id": ref, "label": server.get("description") or ref})
    return {"skills": skills, "mcpServers": servers}


@router.get("")
def list_groups(scope: Scope, tenant_id: str = "") -> list[PermissionGroup]:
    if tenant_id:
        scope.assert_may_tenant(tenant_id)
    rows = get_repository().query_documents(GROUP_COLLECTION, limit=None)
    return [
        PermissionGroup.model_validate({key: value for key, value in row.items() if key != "__id"})
        for row in rows
        if scope.may_tenant(row.get("tenantId")) and (not tenant_id or row.get("tenantId") == tenant_id)
    ]


def _save(body: PermissionGroup, scope: Scope, group_id: str = "") -> PermissionGroup:
    _tenant(body.tenant_id, scope)
    repository = get_repository()
    previous = repository.get_document(GROUP_COLLECTION, group_id) if group_id else None
    if group_id and previous is None:
        raise HTTPException(404, "权限组不存在")
    if previous:
        scope.assert_may_tenant(previous["tenantId"])
    if previous and previous["tenantId"] != body.tenant_id:
        raise HTTPException(422, "不能移动权限组的租户")
    if body.role == "tenant-admin" or (previous or {}).get("role") == "tenant-admin":
        scope.assert_platform()
    available = resources(body.tenant_id, scope)
    if set(body.skills) - {row["id"] for row in available["skills"]} or set(body.mcp_servers) - {
        row["id"] for row in available["mcpServers"]
    }:
        raise HTTPException(422, "所选资源必须同时获得租户和当前 Root 授权")
    saved = body.model_copy(
        update={
            "id": group_id or str(uuid.uuid4()),
            "skills": sorted(set(body.skills)),
            "mcp_servers": sorted(set(body.mcp_servers)),
        }
    )
    repository.set_document(GROUP_COLLECTION, saved.id, saved.model_dump(by_alias=True))
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email,
        actor_tenant_id=scope.user.tenant_id,
        tenant_id=saved.tenant_id,
        action="save_permission_group",
        target=saved.id,
        before=previous,
        after=saved.model_dump(by_alias=True),
    )
    return saved


@router.post("", status_code=201)
def create_group(body: PermissionGroup, scope: Scope) -> PermissionGroup:
    if body.id:
        raise HTTPException(422, "权限组编号由系统生成")
    return _save(body, scope)


@router.put("/{group_id}")
def update_group(group_id: str, body: PermissionGroup, scope: Scope) -> PermissionGroup:
    return _save(body, scope, group_id)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: str, scope: Scope) -> None:
    repository = get_repository()
    previous = repository.get_document(GROUP_COLLECTION, group_id)
    if previous is None:
        raise HTTPException(404, "权限组不存在")
    scope.assert_may_tenant(previous["tenantId"])
    if previous.get("role") == "tenant-admin":
        scope.assert_platform()
    repository.delete_document(GROUP_COLLECTION, group_id)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email,
        actor_tenant_id=scope.user.tenant_id,
        tenant_id=previous["tenantId"],
        action="delete_permission_group",
        target=group_id,
        before=previous,
    )
