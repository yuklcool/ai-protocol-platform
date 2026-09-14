"""Provider-neutral binary object storage contract.

The database owns metadata and authorization.  Object storage owns bytes only.
Business code addresses an object by ``(tenant_id, key)`` so every adapter has
an explicit tenant boundary instead of relying on bucket/container naming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """Stable information returned by storage adapters."""

    tenant_id: str
    key: str
    size: int
    uri: str


class ObjectStorage(Protocol):
    """Minimal binary-storage boundary used by documents and artifacts.

    Implementations must treat ``tenant_id`` as a hard namespace boundary and
    must reject keys that can escape that namespace.  The interface deliberately
    avoids signed URLs: local storage is served through authenticated application
    routes, while remote adapters may add provider-specific URL helpers later.
    """

    def put_bytes(self, tenant_id: str, key: str, data: bytes) -> ObjectInfo: ...

    def get_bytes(self, tenant_id: str, key: str) -> bytes: ...

    def iter_bytes(
        self,
        tenant_id: str,
        key: str,
        *,
        chunk_size: int = 1024 * 1024,
    ): ...

    def exists(self, tenant_id: str, key: str) -> bool: ...

    def delete(self, tenant_id: str, key: str) -> None: ...

    def list_objects(self, tenant_id: str, *, prefix: str = "") -> list[ObjectInfo]: ...
