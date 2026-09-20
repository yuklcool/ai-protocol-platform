"""Session bootstrap — pre-create tenant-scoped ChatSessionIndex + ADK session.

Called before the first agent turn so iframe/A2UI context has a durable index
row to bind to. Bootstrap is idempotent only inside the authenticated tenant;
a reused session id from another tenant is rejected before any ADK session is
touched.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from adk.agui import APP_NAME, ROOT_AGENT_APP_NAME
from adk.session import get_session_service
from auth import User, get_current_user
from db.chat_sessions import create_session_index, get_session_index, owner_domain_of, session_in_tenant
from db.models.access import AccessControl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


class BootstrapRequest(BaseModel):
    skill_id: str
    document_ids: list[str] = Field(default_factory=list)
    agent_id: str = "aitana_platform"


class BootstrapResponse(BaseModel):
    session_id: str
    created: bool


@router.post("/sessions/{session_id}/bootstrap", response_model=BootstrapResponse)
async def bootstrap_session(
    session_id: str,
    body: BootstrapRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> BootstrapResponse:
    """Pre-create a session inside the caller's stable tenant scope."""
    ctx = request.state.access
    existing = get_session_index(session_id)
    if existing is not None:
        if not session_in_tenant(existing, ctx.tenant_id):
            # Do not disclose whether a foreign tenant owns this opaque id.
            raise HTTPException(status_code=403, detail="Session unavailable in this tenant")
        if existing.owner_uid != user.uid:
            raise HTTPException(status_code=403, detail="Session owned by another user")
        return BootstrapResponse(session_id=session_id, created=False)

    try:
        create_session_index(
            session_id=session_id,
            skill_id=body.skill_id,
            owner_uid=user.uid,
            tenant_id=ctx.tenant_id,
            owner_domain=owner_domain_of(user.email),
            access_control=AccessControl(type="private"),
            document_ids=body.document_ids,
            agent_id=body.agent_id,
            app_name=ROOT_AGENT_APP_NAME if body.agent_id == "root-agent" else APP_NAME,
            provisional=True,
        )
    except (ValueError, PermissionError) as exc:
        logger.warning("session_bootstrap: tenant boundary rejected %s: %s", session_id, exc)
        raise HTTPException(status_code=403, detail="Session unavailable in this tenant") from exc

    session_service = get_session_service()
    try:
        await session_service.create_session(
            app_name=ROOT_AGENT_APP_NAME if body.agent_id == "root-agent" else APP_NAME,
            user_id=user.uid,
            session_id=session_id,
        )
    except Exception:
        logger.warning(
            "session_bootstrap: ADK create_session failed for %s (index still created)",
            session_id,
        )

    logger.info(
        "session_bootstrap: pre-created session %s for skill %s tenant=%s",
        session_id,
        body.skill_id,
        ctx.tenant_id,
    )
    return BootstrapResponse(session_id=session_id, created=True)
