"""Host endpoint for MCP App ``ui/update-model-context`` pushes.

Architecture (sprint 1.25, design doc
docs/archive/design/v6.1.0/mcp-app-update-model-context.md):

The MCP Apps spec defines TWO iframe→host RPC channels — sprint 1.7 wired
the first (``ui/message`` → synthetic chat turns); this module wires the
second. When an MCP App iframe (e.g. the Cesium globe in
ext-apps/map-server) finishes positioning its view, it sends
``ui/update-model-context`` over the bridge with structured content
describing the current iframe state (view UUID, current bounds, label).
The frontend ``<AppRenderer onUpdateModelContext>`` callback POSTs that
content here; we validate, gate, and write it into the ADK session state
under a namespaced key (``mcp_app_context.{server_id}.{tool_name}``) so
the agent's NEXT turn can reference what's currently on screen.

Without this endpoint the iframe receives ``MCP error -32601: No handler
for method`` from the host bridge — non-fatal but pollutes the console
and leaves the agent blind to iframe state, which collapses the
multi-turn workshop demo ("now zoom to its old town" → confused).

授权边界:验证身份和会话归属后,按当前租户 Root 的交互开关、MCP
绑定及服务器启用状态验证。Skill 不再持有 MCP 连接或 context-writes 授权。

Threat model (see design doc Conflict Justifications):
  * The endpoint receives JSON from a trusted host context (the host's
    own React handler) which got it from a sandboxed iframe via
    postMessage. The iframe origin is checked at three boundaries
    upstream (sandbox referrer, sandbox→host postMessage origin,
    host→sandbox postMessage origin). This endpoint adds the auth +
    skill-access + per-server opt-in checks.
  * The merged content goes into a NAMESPACED key
    (``mcp_app_context.{server_id}.{tool_name}``); the agent prompt
    template references this namespace explicitly with framing prose
    so the model treats it as iframe-state data, not user
    instructions. Stops malicious iframe content from poisoning
    arbitrary session keys.
  * 4 KB cap on serialized ``structuredContent`` prevents context
    flooding.

Errors:
  * 400 — schema mismatch (e.g. structuredContent not a dict)
  * 401 — missing/invalid Firebase JWT (handled upstream)
  * 403 — any of the four allowlist/access gates failed
  * 404 — session_id not in the index
  * 413 — structuredContent serialized > 4 KB
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from google.adk.events import Event, EventActions
from pydantic import BaseModel, Field

from adk.session import get_session_service
from auth import User, get_current_user
from db.chat_sessions import app_name_for_session, get_session_index
from db.models.chat_session import ChatSessionIndex
from db.persistence import get_document
from protocols._a2ui_surface_shared import _enforce_root_interaction
from tools.mcp.tenant_scope import mcp_config_visible_to_tenant

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["iframe-context"])

# Hard cap on structuredContent size in serialized JSON bytes. 4 KB is
# generous for typical iframe state (view UUIDs + bounds + label) and
# tight enough to make context flooding uneconomical. Tune later if a
# real widget needs more.
_MAX_STRUCTURED_CONTENT_BYTES = 4096

# Session-state key namespace where iframe pushes land. The agent prompt
# template references this namespace explicitly so the model has framing
# context that this is iframe-supplied state, not user instructions.
_STATE_KEY_NAMESPACE = "mcp_app_context"


class IframeContextRequest(BaseModel):
    """The body of ``POST /api/sessions/{id}/iframe-context``."""

    server_id: str = Field(alias="serverId", min_length=1, max_length=128)
    tool_name: str = Field(alias="toolName", min_length=1, max_length=128)
    # ``structuredContent`` mirrors the ``ui/update-model-context``
    # spec param of the same name. ``content`` is its multi-block
    # cousin (text/image/etc) — we accept the field for forward-compat
    # but don't currently merge it into state (most iframes use
    # structuredContent in practice; if a widget needs content blocks
    # we can extend the merge logic without a wire change).
    structured_content: dict[str, Any] | None = Field(default=None, alias="structuredContent")
    content: list[Any] | None = Field(default=None)

    model_config = {"populate_by_name": True, "extra": "forbid"}


def _require_session(session_id: str) -> ChatSessionIndex:
    idx = get_session_index(session_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return idx


def _enforce_size_cap(structured_content: dict[str, Any] | None) -> str:
    """Gate 7: serialize structured_content and reject if it's larger
    than the cap. Returns the serialized bytes count for logging."""
    if structured_content is None:
        return "0"
    try:
        serialized = json.dumps(structured_content, default=str)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"structuredContent is not JSON-serializable: {exc}",
        ) from exc
    size = len(serialized.encode("utf-8"))
    if size > _MAX_STRUCTURED_CONTENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"structuredContent is {size} bytes; max is {_MAX_STRUCTURED_CONTENT_BYTES}"),
        )
    return str(size)


@router.post("/{session_id}/iframe-context", status_code=204)
async def post_iframe_context(
    session_id: str,
    body: IframeContextRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Receive an iframe ``ui/update-model-context`` push and write it
    into the session's ADK state under
    ``mcp_app_context.{server_id}.{tool_name}``.

    See module docstring for the auth + allowlist + size contract.
    """
    # Gate 2: session exists
    idx = _require_session(session_id)

    # Gate 3: caller can access the session (same 5-type policy as the
    # existing GET /sessions/{id} endpoint)
    ctx = request.state.access
    if not ctx.can_access(idx):
        log.info(
            "iframe_context: access denied uid=%s session_id=%s skill_id=%s",
            user.uid,
            session_id,
            idx.skill_id,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    root_skill = _enforce_root_interaction(idx, user, request, "allow_surface_context_writes")
    servers = root_skill.skill_metadata.tool_configs["mcp"]["servers"]
    if body.server_id not in servers:
        raise HTTPException(403, "MCP server is not bound to the Root Agent")
    if not mcp_config_visible_to_tenant(get_document("mcp_servers", body.server_id), ctx.tenant_id):
        raise HTTPException(403, "MCP server is unavailable")

    # Gate 7: size cap
    size_bytes = _enforce_size_cap(body.structured_content)

    # If both content blocks were absent treat as a no-op rather than
    # writing an empty object — keeps state tidy for buggy senders.
    if body.structured_content is None and not body.content:
        log.info(
            "iframe_context: empty payload, no-op uid=%s session=%s server=%s tool=%s",
            user.uid,
            session_id,
            body.server_id,
            body.tool_name,
        )
        return None

    # Build the namespaced state key. Two-level namespace
    # (server_id.tool_name) so multiple tools from the same server can
    # each push their own latest state without overwriting each other.
    state_key = f"{_STATE_KEY_NAMESPACE}.{body.server_id}.{body.tool_name}"
    state_value: dict[str, Any] = {}
    if body.structured_content is not None:
        state_value["structuredContent"] = body.structured_content
    if body.content:
        state_value["content"] = body.content
    state_value["_pushedAt"] = time.time()

    # Write via ADK's append_event(state_delta) pattern — same as
    # ag_ui_adk's session_manager.update_session_state. We use author
    # "user" (not "system") because ADK's _find_agent_to_run logs a
    # warning for "system" author events.
    # ADK sessions are keyed by ("aitana_platform", user_id, session_id) —
    # build_agui_adk_agent passes the canonical APP_NAME, NOT the skill_id.
    # (Latent bug fixed 2026-05-18: lookups under skill_id always returned
    # None in production; mocked tests didn't catch it. The 7-gate session-
    # index check above already proves the caller's authority; this is
    # purely the storage key.)
    session_service = get_session_service()
    session = await session_service.get_session(
        app_name=app_name_for_session(idx),
        user_id=user.uid,
        session_id=session_id,
    )
    if session is None:
        log.info(
            "iframe_context: ADK session not found uid=%s session_id=%s "
            "skill_id=%s (index exists, ADK session missing)",
            user.uid,
            session_id,
            idx.skill_id,
        )
        raise HTTPException(status_code=404, detail="Session backend not found")

    actions = EventActions(state_delta={state_key: state_value})
    event = Event(
        invocation_id=f"iframe_context_{int(time.time() * 1000)}",
        author="user",
        actions=actions,
        timestamp=time.time(),
    )
    await session_service.append_event(session, event)

    log.info(
        "iframe_context: write uid=%s session=%s skill=%s server=%s tool=%s bytes=%s",
        user.uid,
        session_id,
        idx.skill_id,
        body.server_id,
        body.tool_name,
        size_bytes,
    )
    return None


__all__ = ["router"]
