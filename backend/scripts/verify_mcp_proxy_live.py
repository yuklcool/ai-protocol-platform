#!/usr/bin/env python3
"""Verify a real MCP session through the platform's authenticated MCP proxy.

This script is intentionally a protocol client, not an HTTP status probe.  It
uses the same Python MCP SDK as the backend diagnostics to perform initialize,
tools/list, resources/list and resources/read through ``/mcp/{server_id}``.
The Bearer token authenticates at the platform proxy and must never be forwarded
as the upstream server credential.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return value


def _resource_uri(resource: Any) -> str:
    if hasattr(resource, "uri"):
        return str(resource.uri)
    if isinstance(resource, dict):
        return str(resource.get("uri") or "")
    return ""


def _content_mime(item: Any) -> str:
    if hasattr(item, "mimeType"):
        return str(getattr(item, "mimeType") or "")
    if hasattr(item, "mime_type"):
        return str(getattr(item, "mime_type") or "")
    if isinstance(item, dict):
        return str(item.get("mimeType") or item.get("mime_type") or "")
    return ""


def _content_text(item: Any) -> str:
    if hasattr(item, "text"):
        return str(getattr(item, "text") or "")
    if isinstance(item, dict):
        return str(item.get("text") or "")
    return ""


async def verify(proxy_url: str, token: str, expected_resource_uri: str = "") -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        # Advertise the MCP Apps UI extension through the proxy just as a real
        # frontend MCP client does.
        "MCP-Protocol-Version": "2025-06-18",
    }
    async with asyncio.timeout(25):
        async with streamablehttp_client(proxy_url, headers=headers) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools_result = await session.list_tools()
                tools = list(getattr(tools_result, "tools", None) or [])
                tool_names = [str(getattr(tool, "name", "")) for tool in tools]
                if not tools:
                    raise RuntimeError("proxy MCP tools/list returned no tools")
                if not any("map" in name.casefold() for name in tool_names):
                    raise RuntimeError(f"expected map tool through proxy, got {tool_names!r}")

                resources_result = await session.list_resources()
                resources = list(getattr(resources_result, "resources", None) or [])
                resource_uris = [_resource_uri(resource) for resource in resources]
                resource_uris = [uri for uri in resource_uris if uri]

                target = expected_resource_uri.strip()
                if target and target not in resource_uris:
                    # Some MCP Apps servers advertise the UI URI from tool _meta
                    # rather than resources/list. resources/read is still the
                    # authoritative proof that the proxy can transport the app.
                    pass
                if not target:
                    target = next((uri for uri in resource_uris if uri.startswith("ui://")), "")
                if not target:
                    raise RuntimeError(
                        "no MCP Apps ui:// resource URI was supplied or discovered through proxy"
                    )

                read_result = await session.read_resource(target)
                contents = list(getattr(read_result, "contents", None) or [])
                html = next(
                    (
                        _content_text(item)
                        for item in contents
                        if _content_mime(item).startswith("text/html") and _content_text(item)
                    ),
                    "",
                )
                if not html:
                    raise RuntimeError(
                        f"resources/read {target!r} returned no non-empty text/html content"
                    )

                return {
                    "ok": True,
                    "server": _dump(initialized),
                    "tools": tool_names,
                    "resources": resource_uris,
                    "uiResource": target,
                    "htmlBytes": len(html.encode("utf-8")),
                }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the authenticated platform MCP proxy")
    parser.add_argument("--proxy-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--resource-uri", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(verify(args.proxy_url, args.token, args.resource_uri))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
