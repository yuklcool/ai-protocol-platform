#!/usr/bin/env python3
"""Copy document collections between persistence backends.

Examples:

  # Firestore -> PostgreSQL
  uv run python scripts/migrate_persistence.py \
      --source firestore --target postgres \
      --database-url postgresql://user:pass@localhost:5432/ai_protocol \
      --collections clients,skills,admin_audit

  # LOCAL_MODE memory -> PostgreSQL is mainly useful in tests because the memory
  # repository is process-local and starts empty in a fresh CLI process.

The migration is deliberately additive/upsert-based. It never deletes target
records. Run with --dry-run first. Collection selection is explicit so a new
upstream collection is never copied accidentally across a trust boundary.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable

from db.repository import Repository
from db.repositories.firestore import FirestoreRepository
from db.repositories.memory import MemoryRepository
from db.repositories.postgres import PostgresRepository


def _repository(kind: str, database_url: str | None) -> Repository:
    if kind == "memory":
        return MemoryRepository()
    if kind == "firestore":
        return FirestoreRepository()
    if kind == "postgres":
        url = (database_url or os.environ.get("DATABASE_URL", "")).strip()
        if not url:
            raise SystemExit("PostgreSQL backend requires --database-url or DATABASE_URL")
        return PostgresRepository(url)
    raise SystemExit(f"Unsupported backend: {kind}")


def _chunks(values: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def migrate_collection(
    source: Repository,
    target: Repository,
    collection: str,
    *,
    dry_run: bool,
    batch_size: int,
) -> tuple[int, int]:
    """Return (seen, written) for one collection."""
    rows = source.query_documents(collection, limit=None)
    written = 0
    for batch in _chunks(rows, batch_size):
        for row in batch:
            doc_id = str(row.get("__id") or "").strip()
            if not doc_id:
                raise RuntimeError(f"{collection}: source row has no __id: {row!r}")
            payload = {key: value for key, value in row.items() if key != "__id"}
            if not dry_run:
                target.set_document(collection, doc_id, payload, merge=True)
            written += 1
    return len(rows), written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate AI Protocol Platform persistence collections")
    parser.add_argument("--source", choices=["memory", "firestore", "postgres"], required=True)
    parser.add_argument("--target", choices=["memory", "firestore", "postgres"], required=True)
    parser.add_argument(
        "--collections",
        required=True,
        help="Comma-separated collection names. Selection is explicit by design.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL used for whichever side is postgres (or DATABASE_URL).",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source == args.target:
        raise SystemExit("source and target must be different backends")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    collections = [item.strip() for item in args.collections.split(",") if item.strip()]
    if not collections:
        raise SystemExit("at least one collection is required")

    source = _repository(args.source, args.database_url)
    target = _repository(args.target, args.database_url)
    if not source.healthcheck():
        raise SystemExit(f"source backend {args.source!r} failed healthcheck")
    if not target.healthcheck():
        raise SystemExit(f"target backend {args.target!r} failed healthcheck")

    mode = "DRY RUN" if args.dry_run else "WRITE"
    total = 0
    print(f"Persistence migration: {args.source} -> {args.target} ({mode})")
    for collection in collections:
        seen, written = migrate_collection(
            source,
            target,
            collection,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
        total += written
        print(f"  {collection}: {seen} source documents, {written} {'would write' if args.dry_run else 'written'}")
    print(f"Done: {total} documents {'validated' if args.dry_run else 'copied'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
