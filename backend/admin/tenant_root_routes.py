"""Platform-admin Root policy overlays and metadata catalogs per tenant."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import PlatformScope
from agents.root_runtime import effective_root_config
from config.platform_config import get_platform_config, update_platform_config
from db.models.root_agent import RootAgentTenantOverride
from db.persistence import get_repository, query_documents
from db.tenants import TenantDirectory

router = APIRouter(prefix="/tenant-root", tags=["admin-tenant-root"])


def _tenant(tenant_id: str) -> None:
    if TenantDirectory(get_repository()).get(tenant_id) is None:
        raise HTTPException(404, "Tenant not found")


@router.get("/{tenant_id}")
def read_override(tenant_id: str, scope: PlatformScope) -> dict:
    _tenant(tenant_id)
    config = get_platform_config().agent
    override = config.tenant_overrides.get(tenant_id)
    return {
        "override": override.model_dump(by_alias=True, exclude_none=True) if override else {},
        "effective": effective_root_config(config, tenant_id).model_dump(by_alias=True),
    }


class OverrideWrite(BaseModel):
    override: RootAgentTenantOverride


@router.put("/{tenant_id}")
def save_override(tenant_id: str, body: OverrideWrite, scope: PlatformScope) -> dict:
    _tenant(tenant_id)
    config = get_platform_config().agent
    before = config.tenant_overrides.get(tenant_id)
    overrides = dict(config.tenant_overrides)
    if body.override.model_dump(exclude_none=True):
        overrides[tenant_id] = body.override
    else:
        overrides.pop(tenant_id, None)
    updated = config.model_copy(deep=True, update={"tenant_overrides": overrides})
    update_platform_config({"agent": updated.model_dump(by_alias=True)}, updated_by=scope.user.uid)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        tenant_id=tenant_id,
        action="update_tenant_root_policy",
        target=tenant_id,
        before=before.model_dump(by_alias=True) if before else None,
        after=body.override.model_dump(by_alias=True, exclude_none=True),
    )
    return read_override(tenant_id, scope)


@router.get("/{tenant_id}/resources")
def tenant_resources(tenant_id: str, scope: PlatformScope) -> dict:
    _tenant(tenant_id)
    from adk.tools import TOOL_CATALOG

    skills = query_documents("skills", limit=None)
    servers = query_documents("mcp_servers", limit=None)
    sources = query_documents("knowledge_sources", filters=[("tenantId", "==", tenant_id)], limit=None)
    return {
        "skills": [
            {"id": row["__id"], "label": row.get("displayName") or row.get("name") or row["__id"]}
            for row in skills
            if row.get("tenantId") == tenant_id or row.get("ownerId") == "aitana-platform"
        ],
        "tools": [{"id": row["name"], "label": row.get("label") or row["name"]} for row in TOOL_CATALOG],
        "mcpServers": [
            {"id": row["__id"], "label": row.get("description") or row["__id"]}
            for row in servers
            if row.get("enabled", True) and (row.get("tenantId") == tenant_id or row.get("scope") == "platform")
        ],
        "knowledge": [{"id": row["__id"], "label": row.get("label") or row["__id"]} for row in sources],
    }
