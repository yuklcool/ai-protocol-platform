"""PostgreSQL implementation of the backend-neutral document repository.

The first self-hosted schema stores each platform document as JSONB under the
same collection/doc-id identity used by the existing Firestore code.  This is
intentional: it lets domain modules move behind the Repository boundary first,
then lets hot domains become normalized SQL tables later without a flag-day
migration.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from db.repositories._document_ops import apply_query
from db.repository import Filter


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required when DATA_BACKEND=postgres")
        self._database_url = database_url

    @staticmethod
    def _driver():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - startup guard covers this in packaged builds
            raise RuntimeError(
                "PostgreSQL persistence requires psycopg. Install the locked backend dependencies."
            ) from exc
        return psycopg, dict_row

    @contextmanager
    def _connect(self):
        psycopg, dict_row = self._driver()
        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            yield conn

    def get_document(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM platform_documents WHERE collection = %s AND doc_id = %s",
                (collection, doc_id),
            )
            row = cur.fetchone()
            return dict(row["data"]) if row else None

    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        merge: bool = False,
    ) -> None:
        payload = json.dumps(data)
        with self._connect() as conn, conn.cursor() as cur:
            if merge:
                cur.execute(
                    """
                    INSERT INTO platform_documents (collection, doc_id, data)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (collection, doc_id) DO UPDATE
                    SET data = platform_documents.data || EXCLUDED.data,
                        updated_at = now()
                    """,
                    (collection, doc_id, payload),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO platform_documents (collection, doc_id, data)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (collection, doc_id) DO UPDATE
                    SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (collection, doc_id, payload),
                )
            conn.commit()

    def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE platform_documents
                SET data = data || %s::jsonb, updated_at = now()
                WHERE collection = %s AND doc_id = %s
                """,
                (payload, collection, doc_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"document {collection}/{doc_id} does not exist")
            conn.commit()

    def delete_document(self, collection: str, doc_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM platform_documents WHERE collection = %s AND doc_id = %s",
                (collection, doc_id),
            )
            conn.commit()

    def query_documents(
        self,
        collection: str,
        *,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        # Phase-2 correctness-first implementation: collection isolation and ID
        # selection happen in SQL, while Firestore-compatible filter/order
        # semantics are evaluated by the shared document helper. This avoids
        # subtly different JSONB casting behavior while domains are still being
        # migrated. Hot queries can gain explicit SQL indexes as they stabilize.
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id, data FROM platform_documents WHERE collection = %s",
                (collection,),
            )
            docs = []
            for row in cur.fetchall():
                data = dict(row["data"])
                data["__id"] = row["doc_id"]
                docs.append(data)
        return apply_query(
            docs,
            filters=filters,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
        )

    def increment_field(self, collection: str, doc_id: str, field: str, amount: int = 1) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM platform_documents WHERE collection = %s AND doc_id = %s FOR UPDATE",
                (collection, doc_id),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"document {collection}/{doc_id} does not exist")
            data = dict(row["data"])
            current = data.get(field, 0)
            if not isinstance(current, (int, float)):
                raise TypeError(f"field {field!r} on {collection}/{doc_id} is not numeric")
            data[field] = current + amount
            cur.execute(
                """
                UPDATE platform_documents
                SET data = %s::jsonb, updated_at = now()
                WHERE collection = %s AND doc_id = %s
                """,
                (json.dumps(data), collection, doc_id),
            )
            conn.commit()

    def healthcheck(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return bool(row and row["ok"] == 1)
