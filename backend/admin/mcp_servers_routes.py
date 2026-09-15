"""Administrative control plane for persisted MCP server registry entries.

This module deliberately manages the same ``mcp_servers`` collection consumed by
``tools.mcp.registry`` and ``protocols.mcp_proxy``.  It never returns header
values: credentials are write-only at the API boundary and audit snapshots are
redacted for the same reason.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.audit import record_admin_action
from admin.scope import Scope
from db.persistence import delete_document, get_document, query_documents, set_document
from tools.mcp.registry import clear_registry_cache
from tools.mcp.tenant_scope import PLATFORM_SCOPE, TENANT_SCOPE, normalize_mcp_scope

router = APIRouter(prefix="/api/admin/mcp-servers", tags=["admin-mcp-servers"])
_COLLECTION = "mcp_servers"
_SERVER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_TRANSPORTS = {"http", "streamable-http", "sse"}


class McpServerWrite(BaseModel):
    url: str
    transport: Literal["http", "streamable-http", "sse"] = "http"
    scope: Literal["platform", "tenant"] = "tenant"
    tenant_id: str | None = None
    headers: dict[str, str] | None = Field(
        default=None,
        description="Write-only upstream headers. Values may use ${ENV_VAR} secret references.",
    )
    description: str = ""


class McpServerView(BaseModel):
    server_id: str
    url: str
    transport: str
    scope: str
    tenant_id: str | None = None
    description: str = ""
    header_names: list[str] = []
    has_credentials: bool = False


def _validate_server_id(server_id: str) -> str:
    value = server_id.strip()
    if not _SERVER_ID_RE.fullmatch(value):
        raise HTTPException(
            status_code=422,
            detail="server_id must be 1-128 characters using letters, numbers, '.', '_' or '-'",
        )
    return value


def _validate_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="MCP URL must be an http(s) URL; localhost, private hosts and Docker service names are allowed",
        )
    return value


def _redacted_snapshot(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    safe = dict(data)
    headers = safe.pop("headers", None)
    safe["headerNames"] = sorted(str(k) for k in headers) if isinstance(headers, dict) else []
    safe["hasCredentials"] = bool(headers)
    safe.pop("__id", None)
    return safe


def _to_view(server_id: str, data: dict[str, Any]) -> McpServerView:
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    return McpServerView(
        server_id=server_id,
        url=str(data.get("url") or ""),
        transport=str(data.get("transport") or "http"),
        scope=normalize_mcp_scope(data),
        tenant_id=str(data.get("tenantId") or "") or None,
        description=str(data.get("description") or ""),
        header_names=sorted(str(k) for k in headers),
        has_credentials=bool(headers),
    )


def _may_read(scope: Scope, data: dict[str, Any]) -> bool:
    resource_scope = normalize_mcp_scope(data)
    if scope.is_platform:
        return True
    if resource_scope == PLATFORM_SCOPE:
        return True
    return resource_scope == TENANT_SCOPE and scope.may_tenant(str(data.get("tenantId") or ""))


def _assert_may_mutate(scope: Scope, data: dict[str, Any]) -> None:
    resource_scope = normalize_mcp_scope(data)
    if resource_scope == PLATFORM_SCOPE:
        scope.assert_platform()
        return
    if resource_scope == TENANT_SCOPE:
        scope.assert_may_tenant(str(data.get("tenantId") or ""))
        return
    # Legacy unscoped records fail closed at runtime and are repairable only by
    # a platform admin, never by a tenant admin guessing ownership.
    scope.assert_platform()


@router.get("", response_model=list[McpServerView])
def list_mcp_servers(scope: Scope) -> list[McpServerView]:
    result: list[McpServerView] = []
    for raw in query_documents(_COLLECTION):
        data = dict(raw)
        server_id = str(data.pop("__id", "") or data.pop("serverId", ""))
        if not server_id or not _may_read(scope, data):
            continue
        result.append(_to_view(server_id, data))
    result.sort(key=lambda row: row.server_id.casefold())
    return result


@router.get("/{server_id}", response_model=McpServerView)
def get_mcp_server(server_id: str, scope: Scope) -> McpServerView:
    server_id = _validate_server_id(server_id)
    data = get_document(_COLLECTION, server_id)
    if data is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if not _may_read(scope, data):
        # Do not disclose existence of another tenant's private endpoint.
        raise HTTPException(status_code=404, detail="MCP server not found")
    return _to_view(server_id, data)


@router.put("/{server_id}", response_model=McpServerView)
def upsert_mcp_server(server_id: str, body: McpServerWrite, scope: Scope) -> McpServerView:
    server_id = _validate_server_id(server_id)
    url = _validate_url(body.url)
    transport = body.transport.strip().lower()
    if transport not in _ALLOWED_TRANSPORTS:
        raise HTTPException(status_code=422, detail="Unsupported MCP transport")

    tenant_id = (body.tenant_id or "").strip().casefold()
    if body.scope == PLATFORM_SCOPE:
        scope.assert_platform()
        tenant_id = ""
    else:
        if not tenant_id:
            # A tenant admin may omit tenant_id because their scope contains a
            # single stable tenant id. Platform admins must be explicit.
            if scope.tenant_ids is not None and len(scope.tenant_ids) == 1:
                tenant_id = next(iter(scope.tenant_ids))
            else:
                raise HTTPException(status_code=422, detail="tenant_id is required for tenant-scoped MCP servers")
        scope.assert_may_tenant(tenant_id)

    before = get_document(_COLLECTION, server_id)
    if before is not None:
        _assert_may_mutate(scope, before)

    data: dict[str, Any] = {
        "url": url,
        # Registry treats non-SSE transports as Streamable HTTP; retain the
        # explicit value so the admin UI can accurately show operator intent.
        "transport": transport,
        "scope": body.scope,
        "description": body.description.strip(),
    }
    if tenant_id:
        data["tenantId"] = tenant_id
    if body.headers is not None:
        data["headers"] = {str(k).strip(): str(v) for k, v in body.headers.items() if str(k).strip()}
    elif before is not None and isinstance(before.get("headers"), dict):
        # Omitted credentials mean "keep existing". Send {} to explicitly clear.
        data["headers"] = dict(before["headers"])

    set_document(_COLLECTION, server_id, data, merge=False)
    clear_registry_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        tenant_id=tenant_id,
        action="upsert_mcp_server",
        target=server_id,
        before=_redacted_snapshot(before),
        after=_redacted_snapshot(data),
    )
    return _to_view(server_id, data)


@router.delete("/{server_id}", response_model=McpServerView)
def delete_mcp_server(server_id: str, scope: Scope) -> McpServerView:
    server_id = _validate_server_id(server_id)
    data = get_document(_COLLECTION, server_id)
    if data is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    _assert_may_mutate(scope, data)

    tenant_id = str(data.get("tenantId") or "").strip().casefold()
    delete_document(_COLLECTION, server_id)
    clear_registry_cache()
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        tenant_id=tenant_id,
        action="delete_mcp_server",
        target=server_id,
        before=_redacted_snapshot(data),
        after=None,
    )
    return _to_view(server_id, data)


__all__ = ["router"]
