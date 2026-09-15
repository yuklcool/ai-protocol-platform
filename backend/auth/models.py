"""Provider-neutral authentication models.

No cloud/provider SDK may be imported from this module. Keeping the shared
``User`` contract here lets Self-host/local-JWT code run without importing
Firebase Admin, while Firebase/OIDC/other providers can adapt their verified
identity into the same shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Authenticated caller after provider verification.

    ``tenant_id`` is the stable tenant primary key. It is deliberately
    independent from ``domain`` so OIDC/JWT identities without email, and
    tenants owning multiple email domains, can share the same tenant scope.

    During the migration from the legacy domain-based model providers may leave
    ``tenant_id`` empty; ``build_access_context`` then falls back to ``domain``.
    This keeps existing installations compatible while new identity providers
    and local accounts can populate an explicit tenant id immediately.

    ``group_tags`` and all tenant/domain attributes must come from a trusted
    server-side source. The model itself does not imply how identity was
    verified.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    email: str = ""
    domain: str = ""
    tenant_id: str = ""
    group_tags: frozenset[str] = Field(default_factory=frozenset)
    auth_mode: str = "firebase"
    group_id: str = ""


__all__ = ["User"]