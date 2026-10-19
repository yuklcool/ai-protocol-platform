"""Shared gate logic for the A2UI surface-action endpoints.

Two endpoints share these helpers:

  * ``a2ui_surface_action_routes`` (sprint 2.10) — the original
    fire-and-forget action persistence endpoint.
  * ``a2ui_surface_action_run_routes`` (ACTION-TRIGGER M1) — the bundled
    write-and-run endpoint that, in addition to the action write, kicks
    off an agent turn and streams AG-UI events back.

Pulling the gate primitives here keeps both endpoints honouring exactly
the same access policy. Behaviour-preserving refactor — see
docs/design/v6.1.0/action-triggered-agent-turn.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException

from agents.root_runtime import (
    RootCapabilityDenied,
    compose_root_skill,
    resolve_root_capability,
)
from auth import User
from auth.capability_access import authorized_root_config
from config.platform_config import PlatformConfigUnavailable, get_platform_config
from db.chat_sessions import get_session_index
from db.models import SkillConfig
from db.models.chat_session import ChatSessionIndex

log = logging.getLogger(__name__)

# Hard cap on action.context size. 4 KB matches the iframe-context
# limit — same threat model, same trade-off.
_MAX_CONTEXT_BYTES = 4096

# Session-state key namespace. Must match the prefix in
# adk/a2ui_surface_context.py — both ends anchor on this string.
_STATE_KEY_NAMESPACE = "a2ui_surface_context"


def _require_session(session_id: str) -> ChatSessionIndex:
    """Gate 2: the session must exist in the index. 404 if not.

    Raises:
        HTTPException(404): when the session id is unknown.
    """
    idx = get_session_index(session_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return idx


def _root_runtime_for_session(
    idx: ChatSessionIndex,
    user: User,
    request: Any,
) -> tuple[Any, SkillConfig]:
    """每次回调都读取当前 Root 和用户授权, 历史会话同样需要通过能力检查。"""
    access = request.state.access
    if not access.is_owner(idx):
        raise HTTPException(status_code=403, detail="Shared conversations are read-only")
    try:
        config = authorized_root_config(get_platform_config().agent, user)
    except PlatformConfigUnavailable as exc:
        raise HTTPException(status_code=503, detail="Root Agent policy is temporarily unavailable") from exc
    try:
        capability = resolve_root_capability(config, user, access, idx.skill_id)
    except RootCapabilityDenied as exc:
        raise HTTPException(status_code=403, detail="Root Agent capability is not available") from exc
    return config, compose_root_skill(capability, config)


def _enforce_root_interaction(
    idx: ChatSessionIndex,
    user: User,
    request: Any,
    flag: str,
) -> SkillConfig:
    """Enforce the current Root Agent policy for every A2UI/MCP callback."""
    runtime = _root_runtime_for_session(idx, user, request)
    config, composed = runtime
    if not config.interaction.a2ui_enabled or not getattr(config.interaction, flag, False):
        raise HTTPException(status_code=403, detail="Root Agent interaction is not permitted")
    return composed


def _enforce_size_cap(context: dict[str, Any] | None) -> str:
    """Gate 7: serialize action.context and reject if it's larger than
    the cap. Returns the serialized bytes count for logging.

    Raises:
        HTTPException(400): when context is not JSON-serializable.
        HTTPException(413): when serialized context exceeds the cap.
    """
    if context is None:
        return "0"
    try:
        serialized = json.dumps(context, default=str)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"action.context is not JSON-serializable: {exc}",
        ) from exc
    size = len(serialized.encode("utf-8"))
    if size > _MAX_CONTEXT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"action.context is {size} bytes; max is {_MAX_CONTEXT_BYTES}",
        )
    return str(size)


__all__ = [
    "_MAX_CONTEXT_BYTES",
    "_STATE_KEY_NAMESPACE",
    "_enforce_root_interaction",
    "_enforce_size_cap",
    "_require_session",
    "_root_runtime_for_session",
]
