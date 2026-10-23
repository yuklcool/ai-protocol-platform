from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, get_current_user
from auth.access_context import AccessContext
from observability.user_context import set_user_context
from protocols.sessions_route import router


def document(session_id, owner="alice", **overrides):
    return {
        "sessionId": session_id,
        "ownerUid": owner,
        "skillId": "root-agent",
        "accessControl": {"type": "private"},
        "title": "照明 Energy report",
        "firstMessageAt": datetime(2026, 10, 1, tzinfo=UTC).isoformat(),
        "lastMessageAt": datetime(2026, 10, 20, tzinfo=UTC).isoformat(),
        **overrides,
    }


def client(owner="alice"):
    app = FastAPI()
    user = User(uid=owner)

    @app.middleware("http")
    async def access(request: Request, call_next):
        request.state.access = AccessContext(uid=owner)
        set_user_context(user)
        return await call_next(request)

    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(router)
    # Labels are not relevant to metadata search or ownership.
    with patch("protocols.sessions_route.resolve_skill_labels", return_value={}):
        yield TestClient(app)
