"""Durable admission for one-time confirmations and transport retries."""

import hashlib
import json

from fastapi import HTTPException
from google.adk.sessions.base_session_service import GetSessionConfig

from adk.callbacks import A2UI_SURFACE_STATE_PREFIX
from adk.session import get_session_service
from db.chat_sessions import app_name_for_session
from db.persistence import get_repository
from observability.user_context import authorized_resource_user


async def claim_action(idx, surface_id: str, request_id: str | None) -> None:
    with authorized_resource_user(idx.owner_uid):
        session = await get_session_service().get_session(
            app_name=app_name_for_session(idx),
            user_id=idx.owner_uid,
            session_id=idx.session_id,
            config=GetSessionConfig(num_recent_events=1),
        )
    state = getattr(session, "state", {}) or {}
    raw = state.get(f"{A2UI_SURFACE_STATE_PREFIX}{surface_id}")
    try:
        saved = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, "Saved form is unavailable. Reopen the conversation.") from exc
    artifact = saved.get("artifact") if isinstance(saved, dict) else None
    if isinstance(artifact, dict) and artifact.get("displayOnly"):
        raise HTTPException(409, "This surface is display-only")
    one_time = isinstance(artifact, dict) and artifact.get("kind") in {"elicitation", "obligation-elicitation-form"}
    key = f"surface:{surface_id}" if one_time else f"request:{request_id}" if request_id else None
    if key is None:
        return
    claim_id = hashlib.sha256(f"{idx.session_id}\0{key}".encode()).hexdigest()
    if not get_repository().create_document(
        "surface_action_claims",
        claim_id,
        {
            "sessionId": idx.session_id,
            "ownerUid": idx.owner_uid,
            "surfaceId": surface_id,
        },
    ):
        raise HTTPException(
            409, "Action already submitted. Check the conversation before continuing; it will not be replayed."
        )
