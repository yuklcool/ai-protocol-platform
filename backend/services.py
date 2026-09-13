"""Custom ADK service registrations for the self-hosted platform.

ADK's CLI/FastAPI service registry already knows SQL database session services,
but google-adk 1.31.1 has no generic database MemoryService.  Register our
small PostgreSQL implementation under a private URI scheme so ADK-native routes
and the AG-UI skill path use the same durable memory backend.
"""

from __future__ import annotations

import os

from google.adk.cli.service_registry import get_service_registry

from adk.postgres_memory import PostgresMemoryService


def _postgres_memory_factory(uri: str, **kwargs):  # type: ignore[no-untyped-def]
    del uri, kwargs
    database_url = os.environ.get("MEMORY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when MEMORY_BACKEND=postgres")
    return PostgresMemoryService(database_url)


get_service_registry().register_memory_service("aip-postgres-memory", _postgres_memory_factory)
