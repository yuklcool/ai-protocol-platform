"""Skill request processor — orchestrates a single user turn.

Replaces v5's `process_assistant_request()` with an ADK-native flow:

  1. Look up the skill config; 404 if missing *or* not visible to the caller
     (existence leak prevented).
  2. Build a per-user LlmAgent via `adk.agent.create_agent_with_thinking`.
     The heuristic router picks `fast` vs `thinking` from the user message.
  3. Wrap the agent with `ag_ui_adk.ADKAgent`, using the shared singleton
     session service from `adk.session.get_session_service()` so sessions
     persist across requests within the same process.
  4. Construct an AG-UI `RunAgentInput` and yield each translated event
     as a dict.

Deliberately kept thin — the SSE endpoint owns auth, response shaping,
and header handling; this module just produces the event stream.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import RunAgentInput, UserMessage
from google.genai.errors import ClientError
from opentelemetry import trace

from adk import agent_cache as _agent_cache
from adk.agent import _HeuristicRouter, create_agent_with_thinking
from adk.agui import build_agui_adk_agent, stream_agui_events
from adk.model_errors import ErrorClass, ModelTurnError, classify
from adk.session import get_session_service
from auth.access_context import AccessContext
from auth.firebase_auth import User
from budget import BudgetExceededError
from db.models import SkillConfig
from skills.skill_config import get_skill, resolve_skill_ref

logger = logging.getLogger(__name__)

_session_service = get_session_service()


def record_shell_mode(skill: SkillConfig) -> str:
    """Tag the active request span with the skill's resolved page-level shell
    mode (v6.4.0 SHELL-MODES) so Cloud Trace can group sessions by shell.

    A skill with no `shell` block resolves to ``chat-primary`` — the same
    default the frontend ShellRouter applies. Returns the resolved mode.
    Safe when no span is recording (set_attribute is a no-op).
    """
    mode = skill.shell.mode if skill.shell else "chat-primary"
    trace.get_current_span().set_attribute("shell.mode", mode)
    return mode


class SkillNotFoundError(Exception):
    """Raised when a skill is missing OR not visible to the caller.

    The streaming endpoint collapses both cases into a 404 to avoid
    leaking skill existence to users who cannot see them.

    ``reason`` keeps the two apart for the SERVER LOG only — "no skill by that
    ref" and "exists but the caller lacks the tag" need completely different
    fixes, and collapsing them made a tag-gate rejection indistinguishable
    from a typo (2026-08-05: a bare 404 "Skill not found" cost a debugging
    session). It is deliberately NOT echoed to the client, which still gets an
    identical response either way.
    """

    def __init__(self, skill_id: str, reason: str = "missing") -> None:
        super().__init__(f"Skill not found: {skill_id!r} ({reason})")
        self.skill_id = skill_id
        self.ref = skill_id
        self.reason = reason


async def process_skill_request(
    skill_id: str,
    user: User,
    access: AccessContext,
    session_id: str | None,
    message: str,
    attachments: list[dict[str, Any]] | None = None,
    document_ids: list[str] | None = None,
    resumed_session: bool = False,
    a2ui_surface_state: dict[str, Any] | None = None,
) -> AsyncGenerator[dict, None]:
    """Yield AG-UI events for one turn of ``skill_id``.

    The session preflight is intentionally inside this function rather than the
    HTTP route: both the simple ``sessionId`` wire shape and AG-UI's always-set
    ``threadId`` therefore hit the same tenant/ownership boundary before any
    index mutation or ADK SessionService call.
    """
    skill = get_skill(skill_id)
    if skill is None:
        skill = resolve_skill_ref(skill_id, getattr(user, "uid", None))
    if skill is None:
        logger.warning("skill stream: no skill matches ref %r (id or slug)", skill_id)
        raise SkillNotFoundError(skill_id, reason="missing")
    if not access.can_access_skill(skill):
        logger.warning(
            "skill stream: %s (%s) exists but caller uid=%s is not permitted — accessControl=%s caller_tags=%s",
            skill.skill_id,
            getattr(skill, "slug", "") or "",
            getattr(user, "uid", "?"),
            getattr(skill, "access_control", None),
            getattr(access, "group_tags", None),
        )
        raise SkillNotFoundError(skill_id, reason="forbidden")

    skill_id = skill.skill_id
    record_shell_mode(skill)

    thread_id = session_id or f"thread-{uuid.uuid4().hex[:12]}"

    # Phase 3 tenant hard-boundary. Do this BEFORE _ensure_session_index(),
    # agent construction, or ADK SessionService access. AG-UI HttpAgent always
    # supplies threadId, even when the legacy top-level sessionId field is empty,
    # so route-only checks are insufficient. A same uid may legitimately exist
    # in multiple tenants (OIDC federation/service identities); neither uid nor
    # a public/tagged ACL may cross the stable tenant boundary.
    from db.chat_sessions import get_session_index, session_in_tenant

    existing_session = get_session_index(thread_id)
    if existing_session is not None:
        if not session_in_tenant(existing_session, access.tenant_id):
            logger.warning(
                "skill stream: rejected cross-tenant thread reuse thread=%s caller_tenant=%s",
                thread_id,
                access.tenant_id or "(none)",
            )
            yield {
                "type": "RUN_ERROR",
                "message": "This conversation is not available in the current workspace.",
                "code": "SESSION_TENANT_MISMATCH",
            }
            return
        if not access.can_access(existing_session):
            logger.warning("skill stream: rejected inaccessible thread=%s uid=%s", thread_id, user.uid)
            yield {
                "type": "RUN_ERROR",
                "message": "You do not have access to this conversation.",
                "code": "SESSION_ACCESS_DENIED",
            }
            return
        if not access.is_owner(existing_session):
            logger.info("skill stream: rejected write to shared read-only thread=%s uid=%s", thread_id, user.uid)
            yield {
                "type": "RUN_ERROR",
                "message": "This shared conversation is read-only.",
                "code": "SESSION_READ_ONLY",
            }
            return

    _ensure_session_index(thread_id, skill_id, user.uid, document_ids, getattr(user, "email", "") or "")

    agent_or_router, _agent_cache_hit = _agent_cache.get_or_build(
        skill,
        access,
        lambda: create_agent_with_thinking(skill, user, access_context=access),
    )
    logger.debug("skill=%s agent_cache_%s", skill_id, "hit" if _agent_cache_hit else "miss")
    if isinstance(agent_or_router, _HeuristicRouter):
        agent = agent_or_router.pick_agent(message)
        routing_choice = "thinking" if agent is agent_or_router.thinking else "fast"
        logger.info("skill=%s routing=%s", skill_id, routing_choice)
    else:
        agent = agent_or_router
        routing_choice = "single"

    from observability.timing import STAGE_AGENT_FACTORY_DONE, get_current_tracker

    get_current_tracker().mark(STAGE_AGENT_FACTORY_DONE)

    model_used = ""
    raw_model = getattr(agent, "model", None)
    if isinstance(raw_model, str):
        model_used = raw_model
    elif raw_model is not None:
        model_used = getattr(raw_model, "model", "") or str(raw_model)
    get_current_tracker().set_model(model_used, routing_choice)

    agui_agent = build_agui_adk_agent(agent, user_id=user.uid, session_service=_session_service)

    initial_state: dict[str, Any] = {}
    if document_ids:
        initial_state["document_ids"] = list(document_ids)
    if resumed_session:
        initial_state["app:resumed_session"] = True
    if a2ui_surface_state:
        initial_state["a2ui_surface_state"] = a2ui_surface_state
    run_input = RunAgentInput(
        threadId=thread_id,
        runId=f"run-{uuid.uuid4().hex[:8]}",
        state=initial_state,
        messages=[
            UserMessage(
                id=f"msg-{uuid.uuid4().hex[:8]}",
                role="user",
                content=message,
            )
        ],
        tools=[],
        context=[],
        forwardedProps={},
    )

    try:
        async for event in stream_agui_events(agui_agent, run_input):
            yield event
    except BudgetExceededError as exc:
        decision = exc.decision
        logger.warning(
            "skill=%s budget exceeded: identity_value=opaque retry_after=%ss",
            skill_id,
            decision.retry_after_seconds,
        )
        yield {
            "type": "RUN_ERROR",
            "message": decision.message or "Budget exceeded.",
            "code": "BUDGET_EXCEEDED",
            "retry_after_seconds": decision.retry_after_seconds,
        }
    except ClientError as exc:
        message, code = _translate_client_error(exc)
        logger.error("skill=%s upstream API error: %s", skill_id, exc)
        yield {"type": "RUN_ERROR", "message": message, "code": code}
    except ModelTurnError as exc:
        logger.error("skill=%s model turn failed after fallbacks: %s", skill_id, exc)
        yield _model_error_event(exc.error_class)
    except Exception as exc:
        error_class = classify(exc)
        if error_class.provider == "unknown":
            raise
        logger.error(
            "skill=%s model provider error (%s %s): %s",
            skill_id,
            error_class.provider,
            error_class.status,
            exc,
        )
        yield _model_error_event(error_class)


_MODEL_ERROR_MESSAGES = {
    "MODEL_RATE_LIMITED": "The AI model is receiving too many requests right now.",
    "MODEL_UNAVAILABLE": "The AI model for this skill is temporarily unavailable. Try again in a minute.",
    "MODEL_AUTH_FAILED": "The AI model rejected this deployment's credentials. This needs an operator fix.",
    "MODEL_REQUEST_INVALID": "The AI model could not accept this request (it may be too large).",
}


def _model_error_event(error_class: ErrorClass) -> dict:
    event: dict = {
        "type": "RUN_ERROR",
        "message": _MODEL_ERROR_MESSAGES.get(error_class.code, _MODEL_ERROR_MESSAGES["MODEL_UNAVAILABLE"]),
        "code": error_class.code,
    }
    if error_class.retry_after is not None:
        event["retry_after_seconds"] = error_class.retry_after
    return event


def _ensure_session_index(
    thread_id: str,
    skill_id: str,
    owner_uid: str,
    document_ids: list[str] | None,
    owner_email: str = "",
) -> None:
    """Synchronously create/update the chat-session index for this turn.

    Tenant ownership is preflighted by ``process_skill_request`` before this
    helper is reached. Deep mutation helpers independently enforce the current
    tenant context as defense in depth.
    """
    from db.chat_sessions import (
        add_session_documents,
        clear_provisional,
        create_session_index,
        get_session_index,
        owner_domain_of,
        set_session_skill,
    )

    try:
        existing = get_session_index(thread_id)
    except Exception as exc:
        logger.warning("session-index existence check failed for %s: %s", thread_id, exc)
        return

    docs = list(document_ids) if document_ids else []

    if existing is None:
        anchor_doc_id = docs[0] if docs else None
        access_control = _derive_initial_access_control(anchor_doc_id)
        try:
            create_session_index(
                session_id=thread_id,
                skill_id=skill_id,
                owner_uid=owner_uid,
                owner_domain=owner_domain_of(owner_email),
                access_control=access_control,
                document_ids=docs,
            )
            logger.info("chat_sessions/%s index created synchronously (owner=%s)", thread_id, owner_uid)
        except Exception as exc:
            logger.warning("synchronous session-index write failed for %s: %s", thread_id, exc)
        return

    if existing.provisional:
        try:
            clear_provisional(
                thread_id,
                not_after=existing.last_message_at if (existing.turn_count or 0) > 0 else None,
            )
        except Exception as exc:
            logger.warning("session-index provisional clear failed for %s: %s", thread_id, exc)

    if existing.skill_id != skill_id:
        try:
            set_session_skill(thread_id, skill_id, existing.skill_id)
            logger.info(
                "chat_sessions/%s skill follows turn: %s -> %s",
                thread_id,
                existing.skill_id,
                skill_id,
            )
        except Exception as exc:
            logger.warning("session-index skill-follow update failed for %s: %s", thread_id, exc)

    if docs:
        try:
            add_session_documents(thread_id, docs)
        except Exception as exc:
            logger.warning("synchronous documentIds union failed for %s: %s", thread_id, exc)


def _derive_initial_access_control(document_id: str | None):
    from db.models.access import AccessControl

    if not document_id:
        return AccessControl(type="private")
    try:
        from db.persistence import get_document

        doc = get_document("parsed_documents", document_id)
        if doc and "accessControl" in doc:
            ac_data = doc["accessControl"]
            if isinstance(ac_data, dict):
                return AccessControl.model_validate(ac_data)
    except Exception as exc:
        logger.warning("could not derive access_control for new session: %s", exc)
    return AccessControl(type="private")


def _translate_client_error(exc: ClientError) -> tuple[str, str]:
    status = getattr(exc, "code", None)
    raw = str(exc)
    if status == 401 or "CREDENTIALS_MISSING" in raw or "UNAUTHENTICATED" in raw:
        return (
            "Backend can't authenticate to Vertex AI. "
            "Local dev: run `gcloud auth application-default set-quota-project "
            "$GOOGLE_CLOUD_PROJECT` and restart the backend. "
            "Production: confirm the service account has roles/aiplatform.user.",
            "VERTEX_AUTH_FAILED",
        )
    return (f"Upstream API error ({status or '?'}): {raw}", "UPSTREAM_API_ERROR")
