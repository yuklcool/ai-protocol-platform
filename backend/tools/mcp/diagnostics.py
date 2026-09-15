"""Live MCP connectivity and capability discovery for the admin control plane."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from pydantic import ValidationError

from tools.mcp.registry import _merge_ui_capability_header, _resolve_header_secrets


class McpDiagnosticError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


def _classify_exception(exc: BaseException) -> McpDiagnosticError:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, ValidationError):
        return McpDiagnosticError("schema", text)
    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return McpDiagnosticError("authentication", text)
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)) or "timed out" in lowered or "timeout" in lowered:
        return McpDiagnosticError("network", text)
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, OSError)) or any(
        marker in lowered for marker in ("connection refused", "name or service not known", "nodename nor servname", "dns")
    ):
        return McpDiagnosticError("network", text)
    return McpDiagnosticError("protocol", text or exc.__class__.__name__)


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return value


def _items(result: Any, attr: str) -> list[dict[str, Any]]:
    values = getattr(result, attr, None) or []
    return [_dump(item) for item in values]


def _ui_resource_uris(tools: list[dict[str, Any]], resources: list[dict[str, Any]]) -> list[str]:
    found: set[str] = set()
    for resource in resources:
        uri = str(resource.get("uri") or "")
        mime = str(resource.get("mimeType") or resource.get("mime_type") or "")
        if uri.startswith("ui://") or mime.startswith("text/html"):
            if uri:
                found.add(uri)

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, str(k))
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif isinstance(value, str) and "resourceuri" in key.replace("_", "").lower():
            found.add(value)

    for tool in tools:
        walk(tool)
    return sorted(found)


@asynccontextmanager
async def _session(server_id: str, config: dict[str, Any]) -> AsyncIterator[ClientSession]:
    url = str(config.get("url") or "").strip()
    if not url:
        raise McpDiagnosticError("configuration", "MCP server config has no URL")
    try:
        headers = _merge_ui_capability_header(
            _resolve_header_secrets(server_id, config.get("headers") or {})
        )
    except Exception as exc:
        raise McpDiagnosticError("configuration", str(exc)) from exc

    transport = str(config.get("transport") or "http").lower()
    try:
        if transport == "sse":
            async with sse_client(url, headers=headers) as streams:
                read, write = streams
                async with ClientSession(read, write) as session:
                    yield session
        else:
            async with streamablehttp_client(url, headers=headers) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    yield session
    except McpDiagnosticError:
        raise
    except BaseException as exc:
        raise _classify_exception(exc) from exc


async def discover_mcp_server(
    server_id: str,
    config: dict[str, Any],
    *,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Initialize the server and discover tools/resources/prompts in one session."""
    try:
        async with asyncio.timeout(timeout_seconds):
            async with _session(server_id, config) as session:
                initialize = await session.initialize()
                tools_result = await session.list_tools()
                tools = _items(tools_result, "tools")

                try:
                    resources = _items(await session.list_resources(), "resources")
                except Exception:
                    resources = []
                try:
                    prompts = _items(await session.list_prompts(), "prompts")
                except Exception:
                    prompts = []

                return {
                    "ok": True,
                    "server": _dump(initialize),
                    "tools": tools,
                    "resources": resources,
                    "prompts": prompts,
                    "mcpApps": {
                        "supported": bool(_ui_resource_uris(tools, resources)),
                        "resourceUris": _ui_resource_uris(tools, resources),
                    },
                }
    except McpDiagnosticError:
        raise
    except BaseException as exc:
        raise _classify_exception(exc) from exc


async def check_mcp_server(server_id: str, config: dict[str, Any], *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Health check through a real MCP initialize handshake, not a TCP-only probe."""
    try:
        async with asyncio.timeout(timeout_seconds):
            async with _session(server_id, config) as session:
                initialize = await session.initialize()
                return {"ok": True, "server": _dump(initialize)}
    except McpDiagnosticError:
        raise
    except BaseException as exc:
        raise _classify_exception(exc) from exc


__all__ = ["McpDiagnosticError", "check_mcp_server", "discover_mcp_server"]
