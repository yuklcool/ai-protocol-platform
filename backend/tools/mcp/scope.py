"""Runtime availability of administrator-managed shared MCP servers."""

from typing import Any


def mcp_config_enabled(config: dict[str, Any] | None) -> bool:
    return bool(config) and config.get("enabled", True) is not False and config.get("scope") in (None, "platform")
