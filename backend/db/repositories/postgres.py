"""PostgreSQL implementation of the backend-neutral document repository.

The self-hosted schema stores platform documents as JSONB under the same
collection/doc-id identity used by the Firestore implementation. The public
Repository contract is synchronous; internally this adapter owns one asyncpg
connection pool on a private event-loop thread.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import Future
from typing import Any, Coroutine, TypeVar

from db.repositories._document_ops import apply_query
from db.repository import Filter

_T = TypeVar("_T")


class _LoopRunner:
    """Run asyncpg coroutines on one dedicated event loop from sync callers."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run_loop, name="postgres-repository", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        if self._loop is None:  # pragma: no cover
            raise RuntimeError("PostgreSQL repository event loop did not start")
        future: Future[_T] = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required when DATA_BACKEND=postgres")
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._runner = _LoopRunner()
        self._pool = self._runner.run(self._create_pool())

    async def _create_pool(self):
        import asyncpg

        min_size = max(1, int(os.environ.get("POSTGRES_POOL_MIN_SIZE", "1")))
        max_size = max(min_size, int(os.environ.get("POSTGRES_POOL_MAX_SIZE", "10")))
        return await asyncpg.create_pool(
            dsn=self._database_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=float(os.environ.get("POSTGRES_COMMAND_TIMEOUT", "30")),
        )

    @staticmethod
    def _decode_json(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            value = json.loads(value)
        return dict(value or {})

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        async def op():
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT data FROM platform_documents WHERE collection = $1 AND doc_id = $2",
                    collection,
                    doc_id,
                )
                return self._decode_json(row["data"]) if row else None

        return self._runner.run(op())

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None:
        payload = json.dumps(data)

        async def op():
            async with self._pool.acquire() as conn:
                if merge:
                    await conn.execute(
                        """
                        INSERT INTO platform_documents (collection, doc_id, data)
                        VALUES ($1, $2, $3::jsonb)
                        ON CONFLICT (collection, doc_id) DO UPDATE
                        SET data = platform_documents.data || EXCLUDED.data,
                            updated_at = now()
                        """,
                        collection,
                        doc_id,
                        payload,
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO platform_documents (collection, doc_id, data)
                        VALUES ($1, $2, $3::jsonb)
                        ON CONFLICT (collection, doc_id) DO UPDATE
                        SET data = EXCLUDED.data, updated_at = now()
                        """,
                        collection,
                        doc_id,
                        payload,
                    )

        self._runner.run(op())

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)

        async def op():
            async with self._pool.acquire() as conn:
                status = await conn.execute(
                    """
                    UPDATE platform_documents
                    SET data = data || $1::jsonb, updated_at = now()
                    WHERE collection = $2 AND doc_id = $3
                    """,
                    payload,
                    collection,
                    doc_id,
                )
                if status.endswith(" 0"):
                    raise KeyError(f"document {collection}/{doc_id} does not exist")

        self._runner.run(op())

    def delete_document(self, collection: str, doc_id: str) -> None:
        async def op():
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM platform_documents WHERE collection = $1 AND doc_id = $2",
                    collection,
                    doc_id,
                )

        self._runner.run(op())

    def query_documents(
        self,
        collection: str,
        *,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async def op():
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT doc_id, data FROM platform_documents WHERE collection = $1",
                    collection,
                )
                docs: list[dict[str, Any]] = []
                for row in rows:
                    data = self._decode_json(row["data"])
                    data["__id"] = row["doc_id"]
                    docs.append(data)
                return docs

        docs = self._runner.run(op())
        return apply_query(
            docs,
            filters=filters,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
        )

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        async def op():
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "SELECT data FROM platform_documents WHERE collection = $1 AND doc_id = $2 FOR UPDATE",
                        collection,
                        doc_id,
                    )
                    if not row:
                        raise KeyError(f"document {collection}/{doc_id} does not exist")
                    data = self._decode_json(row["data"])
                    current = data.get(field, 0)
                    if not isinstance(current, (int, float)):
                        raise TypeError(f"field {field!r} on {collection}/{doc_id} is not numeric")
                    data[field] = current + amount
                    await conn.execute(
                        """
                        UPDATE platform_documents
                        SET data = $1::jsonb, updated_at = now()
                        WHERE collection = $2 AND doc_id = $3
                        """,
                        json.dumps(data),
                        collection,
                        doc_id,
                    )

        self._runner.run(op())

    def array_union_field(
        self,
        collection: str,
        doc_id: str,
        field: str,
        values: list[Any],
    ) -> None:
        if not values:
            return

        async def op():
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "SELECT data FROM platform_documents WHERE collection = $1 AND doc_id = $2 FOR UPDATE",
                        collection,
                        doc_id,
                    )
                    if not row:
                        raise KeyError(f"document {collection}/{doc_id} does not exist")
                    data = self._decode_json(row["data"])
                    current = data.get(field, [])
                    if current is None:
                        current = []
                    if not isinstance(current, list):
                        raise TypeError(f"field {field!r} on {collection}/{doc_id} is not an array")
                    merged = list(current)
                    for value in values:
                        if value not in merged:
                            merged.append(value)
                    data[field] = merged
                    await conn.execute(
                        """
                        UPDATE platform_documents
                        SET data = $1::jsonb, updated_at = now()
                        WHERE collection = $2 AND doc_id = $3
                        """,
                        json.dumps(data),
                        collection,
                        doc_id,
                    )

        self._runner.run(op())

    def healthcheck(self) -> bool:
        async def op():
            async with self._pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1

        return bool(self._runner.run(op()))
