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

    ``group_tags`` and tenant/domain attributes must be populated from a
    trusted server-side source. The model itself does not imply how identity
    was verified.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    email: str = ""
    domain: str = ""
    group_tags: frozenset[str] = Field(default_factory=frozenset)
    auth_mode: str = "firebase"
    group_id: str = ""


__all__ = ["User"]
