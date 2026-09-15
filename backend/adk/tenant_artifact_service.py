"""Tenant isolation wrapper for Google ADK ArtifactService.

ADK identifies artifacts by ``app_name / user_id / session_id / filename`` and
has no first-class tenant dimension.  In a multi-tenant platform the same
identity provider uid may legitimately exist in more than one tenant, so user
and session ids alone are not a sufficient storage boundary.

This adapter keeps the public ADK service contract unchanged and injects a
stable, opaque tenant namespace into ``app_name`` before delegating to the real
backend.  Session/Memory user ids therefore remain untouched.

The tenant id comes exclusively from the trusted task-local tenant context set
after authentication.  Missing context fails closed; legacy artifacts created
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

    def _scoped_app_name(self, app_name: str) -> str:
        tenant_id = (self._tenant_resolver() or "").strip()
        if not tenant_id:
            raise PermissionError("stable tenant context is required for artifact access")
        # Never place raw tenant ids in filesystem paths / GCS object keys.
        # 80 bits is ample namespace separation while keeping paths readable.
        digest = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:20]
        return f"tenant-{digest}--{app_name}"

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
        return await self.delegate.save_artifact(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        return await self.delegate.load_artifact(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        return await self.delegate.list_artifact_keys(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        await self.delegate.delete_artifact(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        return await self.delegate.list_versions(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        return await self.delegate.list_artifact_versions(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
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
        return await self.delegate.get_artifact_version(
            app_name=self._scoped_app_name(app_name),
            user_id=user_id,
            filename=filename,
            session_id=session_id,
            version=version,
        )


__all__ = ["TenantScopedArtifactService"]
