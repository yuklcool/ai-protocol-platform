"""Apply bundled PostgreSQL schema migrations for self-host deployments.

The release Compose path must be able to start from prebuilt images without a
checkout that bind-mounts SQL into postgres:/docker-entrypoint-initdb.d.  This
runner executes the SQL files already baked into the backend image and records
each applied filename in ``platform_schema_migrations``.

It is safe to run on every backend start.  Existing installations that already
received 001 through postgres initdb simply execute its idempotent CREATEs once
and then record it in the journal.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"


async def _apply() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for self-host migrations")
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            already_applied = await conn.fetchval(
                "SELECT 1 FROM platform_schema_migrations WHERE version = $1",
                path.name,
            )
            if already_applied:
                continue

            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO platform_schema_migrations(version) VALUES ($1)",
                    path.name,
                )
            print(f"Applied self-host migration: {path.name}", flush=True)
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_apply())


if __name__ == "__main__":
    main()
