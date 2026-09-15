"""Tenant isolation wrapper for Google ADK ArtifactService.

ADK 1.31.1 accepts ``app_name`` on the ArtifactService contract, but its local
``FileArtifactService`` storage key does *not* include app_name; the on-disk
layout is keyed by ``user_id / session_id / filename``.  Newer ADK releases add
an app-name directory, so relying on app_name alone would make tenant isolation
version-dependent.

This adapter therefore namespaces BOTH app_name and the artifact-only user_id
with a stable tenant hash before delegating.  The caller-visible Session/Memory
user id is never changed; only ArtifactService receives the scoped user id.

The tenant id comes exclusively from the trusted task-local tenant context set
after authentication. Missing context fails closed. Legacy artifacts created
before tenant attribution must be migrated explicitly rather than guessed from
email/domain at read time.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Optional, Union

from google.adk.artifacts.base_artifact_service import ArtifactVersion, BaseArtifactService
from google.genai import types

from observability.tenant_context import get_current_tenant_id

TenantResolver = Callable[[], str]


class TenantScopedArtifactService(BaseArtifactService):
    """Delegate ADK artifact operations through a stable tenant namespace."""

    def __init__(
        self,
        delegate: BaseArtifactService,
        *,
        tenant_resolver: TenantResolver = get_current_tenant_id,
    ) -> None:
        self.delegate = delegate
        self._tenant_resolver = tenant_resolver

    def _tenant_hash(self) -> str:
        tenant_id = (self._tenant_resolver() or "").strip()
        if not tenant_id:
            raise PermissionError("stable tenant context is required for artifact access")
        # Never place raw tenant ids in filesystem paths / GCS object keys.
        # 80 bits is ample namespace separation while keeping paths readable.
        return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:20]

    def _scope(self, app_name: str, user_id: str) -> tuple[str, str]:
        digest = self._tenant_hash()
        # Scope both dimensions. ADK 1.31.1 FileArtifactService ignores app_name,
        # while newer File/GCS implementations may include it. Applying the same
        # tenant hash to both keeps isolation stable across backend/version changes.
        return f"tenant-{digest}--{app_name}", f"tenant-{digest}--{user_id}"

    async def save_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        artifact: Union[types.Part, dict[str, Any]],
        session_id: Optional[str] = None,
        custom_metadata: Optional[dict[str, Any]] = None,
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
        session_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[types.Part]:
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
        session_id: Optional[str] = None,
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
        session_id: Optional[str] = None,
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
        session_id: Optional[str] = None,
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
        session_id: Optional[str] = None,
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
        session_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[ArtifactVersion]:
        scoped_app, scoped_user = self._scope(app_name, user_id)
        return await self.delegate.get_artifact_version(
            app_name=scoped_app,
            user_id=scoped_user,
            filename=filename,
            session_id=session_id,
            version=version,
        )


__all__ = ["TenantScopedArtifactService"]
