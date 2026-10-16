"""Partition ADK's app/user state as well as session rows by trusted tenant."""

from __future__ import annotations

import hashlib
from typing import Any

from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse

from observability.tenant_context import get_current_tenant_id


class TenantScopedSessionService(BaseSessionService):
    def __init__(self, delegate: BaseSessionService) -> None:
        self.delegate = delegate

    def _app(self, app_name: str) -> str:
        tenant = get_current_tenant_id()
        if not tenant:
            raise PermissionError("stable tenant context is required for session access")
        digest = hashlib.sha256(tenant.encode()).hexdigest()[:20]
        return f"tenant-{digest}--{app_name}"

    @staticmethod
    def _public(session: Session, app_name: str) -> Session:
        return session.model_copy(update={"app_name": app_name})

    async def create_session(
        self, *, app_name: str, user_id: str, state: dict[str, Any] | None = None, session_id: str | None = None
    ) -> Session:
        session = await self.delegate.create_session(
            app_name=self._app(app_name), user_id=user_id, state=state, session_id=session_id
        )
        return self._public(session, app_name)

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str, config: GetSessionConfig | None = None
    ) -> Session | None:
        session = await self.delegate.get_session(
            app_name=self._app(app_name), user_id=user_id, session_id=session_id, config=config
        )
        return self._public(session, app_name) if session is not None else None

    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> ListSessionsResponse:
        response = await self.delegate.list_sessions(app_name=self._app(app_name), user_id=user_id)
        return response.model_copy(update={"sessions": [self._public(s, app_name) for s in response.sessions]})

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        await self.delegate.delete_session(app_name=self._app(app_name), user_id=user_id, session_id=session_id)

    async def append_event(self, session: Session, event: Event) -> Event:
        scoped = session.model_copy(deep=True, update={"app_name": self._app(session.app_name)})
        result = await self.delegate.append_event(scoped, event)
        # ADK mutates the supplied Session as part of append_event. Preserve
        # that contract while keeping the tenant namespace private to storage.
        session.state = scoped.state
        session.events = scoped.events
        session.last_update_time = scoped.last_update_time
        return result
