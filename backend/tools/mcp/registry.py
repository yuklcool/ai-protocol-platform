"""MCP toolset registry backed by persisted ``mcp_servers`` configs.

Phase-3 tenant rules:
- every config has an explicit ``scope``: ``platform`` or ``tenant``;
- tenant-private configs must carry the exact stable ``tenantId``;
- historical rows with no scope fail closed;
- the in-process TTL cache is keyed by ``(tenant_id, server_id)`` so one
  tenant can never reuse another tenant's resolved endpoint/headers.

Secret-bearing header values of the form ``${ENV_VAR}`` are resolved from the
process environment at build time and never persisted as raw secrets.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from db.persistence import get_document
from observability.tenant_context import get_current_tenant_id
from tools.mcp.tenant_scope import mcp_config_visible_to_tenant, require_stable_tenant_id

log = logging.getLogger(__name__)
_MCP_COLLECTION = "mcp_servers"
_CONFIG_CACHE_TTL = 60.0
_config_cache: dict[tuple[str, str], tuple[float, dict | None]] = {}


def clear_registry_cache() -> None:
    _config_cache.clear()


def _cached_server_config(server_id: str) -> dict | None:
    """Resolve one server config inside the current stable tenant boundary."""
    tenant_id = require_stable_tenant_id(get_current_tenant_id())
    cache_key = (tenant_id, server_id)
    now = time.time()
    entry = _config_cache.get(cache_key)
    if entry is not None and (now - entry[0]) < _CONFIG_CACHE_TTL:
        return entry[1]

    config = get_document(_MCP_COLLECTION, server_id)
    if not mcp_config_visible_to_tenant(config, tenant_id):
        # Cache the tenant-relative miss, never the raw foreign config.
        config = None
    _config_cache[cache_key] = (now, config)
    return config


def derive_in_process_mcp_base_url() -> str:
    override = os.environ.get("MCP_INTERNAL_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    port = os.environ.get("PORT", "1956")
    return f"http://127.0.0.1:{port}"


SERVER_ID_ATTR = "_aitana_mcp_server_id"
UI_CAPABILITY_HEADER = "x-aitana-mcp-ui-supported"
UI_CAPABILITY_MIME_TYPE = "text/html;profile=mcp-app"


class TaggedMcpToolset(McpToolset):
    """McpToolset that tags produced tools with their originating server id."""

    _TOOLS_CACHE_TTL = 300.0

    def __init__(self, *, server_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._aitana_server_id = server_id
        self._tools_cache: tuple[float, list] | None = None

    @property
    def aitana_server_id(self) -> str:
        return self._aitana_server_id

    async def get_tools(self, readonly_context: ReadonlyContext | None = None):  # type: ignore[override]
        cached = self._tools_cache
        if cached is not None and (time.monotonic() - cached[0]) < self._TOOLS_CACHE_TTL:
            return cached[1]
        tools = await super().get_tools(readonly_context=readonly_context)
        for tool in tools:
            try:
                setattr(tool, SERVER_ID_ATTR, self._aitana_server_id)
            except Exception as exc:  # pragma: no cover
                log.debug("mcp_registry: failed to tag tool %r: %s", tool, exc)
        self._tools_cache = (time.monotonic(), tools)
        return tools


def get_mcp_tools(server_ids: list[str]) -> list[McpToolset]:
    resolved, _missing = get_mcp_tools_with_status(server_ids)
    return resolved


def get_mcp_tools_with_status(server_ids: list[str]) -> tuple[list[McpToolset], list[str]]:
    """Resolve only MCP servers visible in the current authenticated tenant."""
    resolved: list[McpToolset] = []
    missing: list[str] = []
    for server_id in server_ids:
        try:
            config = _cached_server_config(server_id)
        except Exception as exc:
            log.warning("mcp_registry: failed to load server config %r: %s", server_id, exc)
            missing.append(server_id)
            continue

        if config is None:
            log.warning(
                "mcp_registry: server %r missing or outside current tenant scope; skipping",
                server_id,
            )
            missing.append(server_id)
            continue

        toolset = _build_toolset(server_id, config)
        if toolset is None:
            missing.append(server_id)
            continue
        resolved.append(toolset)
    return resolved, missing


class UnresolvedHeaderSecret(Exception):
    """A ``${ENV_VAR}`` header reference had no value in the environment."""


_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _resolve_header_secrets(server_id: str, headers: dict) -> dict:
    resolved: dict = {}
    for key, value in headers.items():
        match = _ENV_REF.match(value) if isinstance(value, str) else None
        if match is None:
            resolved[key] = value
            continue
        var_name = match.group(1)
        secret = os.environ.get(var_name, "").strip()
        if not secret:
            raise UnresolvedHeaderSecret(
                f"mcp_servers/{server_id} header {key!r} references ${{{var_name}}} "
                f"but {var_name} is unset or empty; refusing to send a literal placeholder"
            )
        resolved[key] = secret
    return resolved


def _merge_ui_capability_header(headers: dict) -> dict:
    merged = dict(headers) if headers else {}
    merged.setdefault(UI_CAPABILITY_HEADER, UI_CAPABILITY_MIME_TYPE)
    return merged


def _build_toolset(server_id: str, config: dict) -> McpToolset | None:
    url = config.get("url")
    if not url:
        log.warning("mcp_registry: server %r has no url field; skipping", server_id)
        return None

    transport = str(config.get("transport", "http")).lower()
    try:
        server_headers = _resolve_header_secrets(server_id, config.get("headers") or {})
    except UnresolvedHeaderSecret as exc:
        log.error("mcp_registry: %s", exc)
        return None
    headers = _merge_ui_capability_header(server_headers)

    if transport == "sse":
        connection = SseConnectionParams(url=url, headers=headers)
    else:
        connection = StreamableHTTPConnectionParams(url=url, headers=headers)
    return TaggedMcpToolset(server_id=server_id, connection_params=connection)


__all__ = [
    "SERVER_ID_ATTR",
    "TaggedMcpToolset",
    "UI_CAPABILITY_HEADER",
    "UI_CAPABILITY_MIME_TYPE",
    "UnresolvedHeaderSecret",
    "clear_registry_cache",
    "derive_in_process_mcp_base_url",
    "get_mcp_tools",
    "get_mcp_tools_with_status",
]
