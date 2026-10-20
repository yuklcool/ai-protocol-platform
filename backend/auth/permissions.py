"""Tool policy for independent background invocations; Root enforces its own bindings."""

import time
from typing import Any

from db import persistence as fs

COLLECTION = "tool_permissions"
_CACHE_TTL = 60
_cache: dict[tuple[str, str], tuple[float, bool]] = {}


def clear_cache() -> None:
    _cache.clear()


class ToolPermissionDenied(Exception):
    """Raised when a user is not permitted to invoke a tool."""

    def __init__(self, user_email: str, tool_name: str) -> None:
        self.user_email = user_email
        self.tool_name = tool_name
        super().__init__(f"user {user_email} is not permitted to use tool {tool_name}")


def _doc_allows(doc: dict[str, Any], tool_name: str) -> bool:
    return tool_name not in doc.get("denied", []) and ("*" in doc.get("tools", []) or tool_name in doc.get("tools", []))


def can_use_tool(user_email: str, user_domain: str, tool_name: str) -> bool:
    cache_key = (user_email, tool_name)
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]
    for key in (user_email, "*"):
        row = fs.get_document(COLLECTION, key) if key else None
        if row is not None:
            result = _doc_allows(row, tool_name)
            _cache[cache_key] = (time.monotonic(), result)
            return result
    return False
