"""Isolate ADK artifacts by verified user, including backends that ignore app_name."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from google.adk.artifacts.base_artifact_service import ArtifactVersion, BaseArtifactService
from google.genai import types

from observability.user_context import get_resource_user_id

UserResolver = Callable[[], str]


class UserScopedArtifactService(BaseArtifactService):
    """Delegate ADK artifact operations through a stable user namespace."""

    def __init__(
        self,
        delegate: BaseArtifactService,
        *,
        user_resolver: UserResolver = get_resource_user_id,
    ) -> None:
        self.delegate = delegate
        self._user_resolver = user_resolver

    def _user_hash(self) -> str:
        user_id = (self._user_resolver() or "").strip()
        if not user_id:
            raise PermissionError("stable user context is required for artifact access")
        # Never place raw user ids in filesystem paths / GCS object keys.
        # 80 bits is ample namespace separation while keeping paths readable.
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:20]

    def _scope(self, app_name: str, user_id: str) -> tuple[str, str]:
        digest = self._user_hash()
        if user_id != self._user_resolver():
            raise PermissionError("Resource belongs to another user")
        # Scope both dimensions. ADK 1.31.1 FileArtifactService ignores app_name,
        # while newer File/GCS implementations may include it. Applying the same
        # user hash to both keeps isolation stable across backend/version changes.
        return f"user-{digest}--{app_name}", f"user-{digest}--{user_id}"

    async def save_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        artifact: types.Part | dict[str, Any],
        session_id: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> int:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.save_artifact(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            artifact=artifact,
            session_id=session_id,
            custom_metadata=custom_metadata,
        )

    async def load_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: str | None = None,
        version: int | None = None,
    ) -> types.Part | None:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.load_artifact(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
            version=version,
        )

    async def list_artifact_keys(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
    ) -> list[str]:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.list_artifact_keys(
            app_name=scoped_app,
            user_id=scoped_user,
            session_id=session_id,
        )

    async def delete_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: str | None = None,
    ) -> None:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        await self.delegate.delete_artifact(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
        )

    async def list_versions(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: str | None = None,
    ) -> list[int]:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.list_versions(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
        )

    async def list_artifact_versions(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: str | None = None,
    ) -> list[ArtifactVersion]:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.list_artifact_versions(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
        )

    async def get_artifact_version(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: str | None = None,
        version: int | None = None,
    ) -> ArtifactVersion | None:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.get_artifact_version(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
            version=version,
        )


__all__ = ["UserScopedArtifactService"]
