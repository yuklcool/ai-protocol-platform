"""Session bootstrap — pre-create user-scoped ChatSessionIndex + ADK session.

Called before the first agent turn so iframe/A2UI context has a durable index
row to bind to. Bootstrap is idempotent only inside the authenticated user;
a reused session id from another user is rejected before any ADK session is
touched.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from adk.agui import APP_NAME, ROOT_AGENT_APP_NAME
from adk.session import get_session_service
from auth import User, get_current_user
from db.chat_sessions import create_session_index, get_session_index, owner_domain_of
from db.models.access import AccessControl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


class BootstrapRequest(BaseModel):
    skill_id: str
    document_ids: list[str] = Field(default_factory=list)
    agent_id: str = "root-agent"


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
    """Pre-create a session inside the caller's stable user scope."""
    ctx = request.state.access
    existing = get_session_index(session_id)
    if existing is not None:
        if existing.owner_uid != user.uid:
            raise HTTPException(status_code=403, detail="Session owned by another user")
        return BootstrapResponse(session_id=session_id, created=False)

    from tools.documents.access import DocumentUnavailable, validate_selection

    try:
        validate_selection(body.document_ids, user_id=user.uid)
    except DocumentUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        create_session_index(
            session_id=session_id,
            skill_id=body.skill_id,
            owner_uid=user.uid,
            owner_domain=owner_domain_of(user.email),
            access_control=AccessControl(type="private"),
            document_ids=body.document_ids,
            agent_id=body.agent_id,
            app_name=ROOT_AGENT_APP_NAME if body.agent_id == "root-agent" else APP_NAME,
            provisional=True,
        )
    except (ValueError, PermissionError) as exc:
        logger.warning("session_bootstrap: user boundary rejected %s: %s", session_id, exc)
        raise HTTPException(status_code=403, detail="Session unavailable in this user") from exc

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
        "session_bootstrap: pre-created session %s for skill %s user=%s",
        session_id,
        body.skill_id,
        ctx.uid,
    )
    return BootstrapResponse(session_id=session_id, created=True)
