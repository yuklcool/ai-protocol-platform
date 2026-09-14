"""Persistence backend selection and backend-neutral document facade.

Selection rules preserve today's behavior:
- explicit ``DATA_BACKEND`` always wins;
- otherwise LOCAL_MODE -> memory;
- otherwise -> firestore.

PostgreSQL is opt-in through ``DATA_BACKEND=postgres`` + ``DATABASE_URL``.
Domain modules should import this module instead of ``db.firestore``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from config.local_mode import is_local_mode
from db.repository import Filter, Repository

logger = logging.getLogger(__name__)

DataBackend = Literal["memory", "firestore", "postgres"]
_repository: Repository | None = None


def data_backend() -> DataBackend:
    raw = os.environ.get("DATA_BACKEND", "").strip().lower()
    if raw:
        if raw not in {"memory", "firestore", "postgres"}:
            raise RuntimeError(
                f"Unsupported DATA_BACKEND={raw!r}; expected memory, firestore, or postgres"
            )
        return raw  # type: ignore[return-value]
    return "memory" if is_local_mode() else "firestore"


def build_repository(backend: DataBackend | None = None) -> Repository:
    selected = backend or data_backend()
    if selected == "memory":
        from db.repositories.memory import MemoryRepository

        # LOCAL_MODE historically seeds data through db.firestore's in-memory
        # singleton. Inject that client explicitly so the provider-neutral
        # facade sees the same fixtures. Direct MemoryRepository() callers stay
        # isolated and are unaffected by environment variables.
        if is_local_mode():
            from db.firestore import get_client

            return MemoryRepository(client=get_client())
        return MemoryRepository()
    if selected == "firestore":
        from db.repositories.firestore import FirestoreRepository

        return FirestoreRepository()
    if selected == "postgres":
        from db.repositories.postgres import PostgresRepository

        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required when DATA_BACKEND=postgres")
        return PostgresRepository(database_url)
    raise AssertionError(f"unreachable DATA_BACKEND {selected!r}")


def get_repository() -> Repository:
    global _repository
    if _repository is None:
        selected = data_backend()
        _repository = build_repository(selected)
        logger.info("Persistence backend: %s", selected)
    return _repository


def get_tenant_repository(tenant_id: str, *, tenant_field: str = "tenantId") -> Repository:
    """Return a fail-closed tenant-scoped view of the configured repository.

    New tenant-owned domain modules should prefer this helper to manually
    appending ``tenantId`` filters. Legacy collections can continue using the
    unscoped facade until their documents have been migrated to explicit tenant
    ownership.
    """
    from db.tenant_repository import TenantRepository

    return TenantRepository(get_repository(), tenant_id, tenant_field=tenant_field)


def reset_repository_for_testing(repository: Repository | None = None) -> None:
    global _repository
    _repository = repository


def get_document(collection: str, doc_id: str) -> dict[str, Any] | None:
    return get_repository().get_document(collection, doc_id)


def set_document(
    collection: str,
    doc_id: str,
    data: dict[str, Any],
    merge: bool = False,
) -> None:
    get_repository().set_document(collection, doc_id, data, merge=merge)


def update_document(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_repository().update_document(collection, doc_id, data)


def delete_document(collection: str, doc_id: str) -> None:
    get_repository().delete_document(collection, doc_id)


def query_documents(
    collection: str,
    filters: list[Filter] | None = None,
    order_by: str | None = None,
    order_direction: str = "DESCENDING",
    start_after_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return get_repository().query_documents(
        collection,
        filters=filters,
        order_by=order_by,
        order_direction=order_direction,
        start_after_id=start_after_id,
        limit=limit,
    )


def increment_field(collection: str, doc_id: str, field: str, amount: int = 1) -> None:
    get_repository().increment_field(collection, doc_id, field, amount)


def array_union_field(collection: str, doc_id: str, field: str, values: list[Any]) -> None:
    """Atomically append unique values to an array/list field."""
    if not values:
        return
    get_repository().array_union_field(collection, doc_id, field, values)


def persistence_healthcheck() -> bool:
    return get_repository().healthcheck()
