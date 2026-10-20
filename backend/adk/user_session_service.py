"""Partition ADK's app/user state as well as session rows by trusted user."""

from __future__ import annotations

import hashlib
from typing import Any

from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse

from observability.user_context import get_resource_user_id, require_resource_user


class UserScopedSessionService(BaseSessionService):
    def __init__(self, delegate: BaseSessionService) -> None:
        self.delegate = delegate

    def _app(self, app_name: str) -> str:
        user = get_resource_user_id()
        if not user:
            raise PermissionError("stable user context is required for session access")
        digest = hashlib.sha256(user.encode()).hexdigest()[:20]
        return f"user-{digest}--{app_name}"

    @staticmethod
    def _public(session: Session, app_name: str) -> Session:
        return session.model_copy(update={"app_name": app_name})

    async def create_session(
        self, *, app_name: str, user_id: str, state: dict[str, Any] | None = None, session_id: str | None = None
    ) -> Session:
        require_resource_user(user_id)
        session = await self.delegate.create_session(
            app_name=self._app(app_name), user_id=user_id, state=state, session_id=session_id
        )
        return self._public(session, app_name)

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str, config: GetSessionConfig | None = None
    ) -> Session | None:
        require_resource_user(user_id)
        session = await self.delegate.get_session(
            app_name=self._app(app_name), user_id=user_id, session_id=session_id, config=config
        )
        return self._public(session, app_name) if session is not None else None

    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> ListSessionsResponse:
        user_id = require_resource_user(user_id or get_resource_user_id())
        response = await self.delegate.list_sessions(app_name=self._app(app_name), user_id=user_id)
        return response.model_copy(update={"sessions": [self._public(s, app_name) for s in response.sessions]})

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        require_resource_user(user_id)
        await self.delegate.delete_session(app_name=self._app(app_name), user_id=user_id, session_id=session_id)

    async def append_event(self, session: Session, event: Event) -> Event:
        require_resource_user(session.user_id)
        scoped = session.model_copy(deep=True, update={"app_name": self._app(session.app_name)})
        result = await self.delegate.append_event(scoped, event)
        # ADK mutates the supplied Session as part of append_event. Preserve
        # that contract while keeping the user namespace private to storage.
        session.state = scoped.state
        session.events = scoped.events
        session.last_update_time = scoped.last_update_time
        session._storage_update_marker = scoped._storage_update_marker
        return result
