"""Backend-neutral journal and rollback helpers for tenant ownership migration.

The journal intentionally stores only documents created by the migration and
fields explicitly changed on pre-existing documents. In particular it never
snapshots whole ``auth_users`` rows, so password hashes and unrelated identity
metadata are not copied into migration history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from db.repository import Repository

RUN_COLLECTION = "tenant_migration_runs"
OP_COLLECTION = "tenant_migration_operations"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _field_state(document: dict[str, Any], field: str) -> dict[str, Any]:
    if field in document:
        return {"present": True, "value": document[field]}
    return {"present": False}


def _matches_field_state(document: dict[str, Any], field: str, state: dict[str, Any]) -> bool:
    present = bool(state.get("present"))
    if present:
        return field in document and document.get(field) == state.get("value")
    return field not in document


@dataclass
class MigrationJournal:
    repository: Repository
    run_id: str
    _seq: int = 0

    @classmethod
    def start(cls, repository: Repository, *, mapping: dict[str, str]) -> "MigrationJournal":
        run_id = str(uuid.uuid4())
        repository.set_document(
            RUN_COLLECTION,
            run_id,
            {
                "runId": run_id,
                "status": "running",
                "startedAt": _now(),
                "mapping": dict(sorted(mapping.items())),
            },
        )
        return cls(repository=repository, run_id=run_id)

    def _next_id(self) -> tuple[int, str]:
        self._seq += 1
        return self._seq, f"{self.run_id}:{self._seq:06d}"

    def create_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> bool:
        """Create a document idempotently and journal it when newly created."""
        current = self.repository.get_document(collection, doc_id)
        if current is not None:
            if current != data:
                raise ValueError(
                    f"migration conflict: {collection}/{doc_id} already exists with different content"
                )
            return False

        seq, op_id = self._next_id()
        operation = {
            "runId": self.run_id,
            "seq": seq,
            "kind": "create",
            "collection": collection,
            "docId": doc_id,
            "after": data,
            "status": "pending",
        }
        self.repository.set_document(OP_COLLECTION, op_id, operation)
        self.repository.set_document(collection, doc_id, data)
        self.repository.update_document(OP_COLLECTION, op_id, {"status": "applied", "appliedAt": _now()})
        return True

    def update_fields(self, collection: str, doc_id: str, updates: dict[str, Any]) -> bool:
        """Update only selected fields and journal field-level before/after state."""
        if not updates:
            return False
        current = self.repository.get_document(collection, doc_id)
        if current is None:
            raise ValueError(f"migration conflict: {collection}/{doc_id} does not exist")
        changed = {key: value for key, value in updates.items() if current.get(key) != value or key not in current}
        if not changed:
            return False

        before = {field: _field_state(current, field) for field in changed}
        after = {field: {"present": True, "value": value} for field, value in changed.items()}
        seq, op_id = self._next_id()
        operation = {
            "runId": self.run_id,
            "seq": seq,
            "kind": "fields",
            "collection": collection,
            "docId": doc_id,
            "before": before,
            "after": after,
            "status": "pending",
        }
        self.repository.set_document(OP_COLLECTION, op_id, operation)
        self.repository.update_document(collection, doc_id, changed)
        self.repository.update_document(OP_COLLECTION, op_id, {"status": "applied", "appliedAt": _now()})
        return True

    def finish(self, summary: dict[str, Any]) -> None:
        self.repository.update_document(
            RUN_COLLECTION,
            self.run_id,
            {"status": "applied", "finishedAt": _now(), "summary": summary},
        )

    def fail(self, error: Exception) -> None:
        self.repository.update_document(
            RUN_COLLECTION,
            self.run_id,
            {"status": "failed", "finishedAt": _now(), "error": str(error)[:2000]},
        )


def _operations(repository: Repository, run_id: str) -> list[dict[str, Any]]:
    # Query only by run id and sort in Python. This avoids requiring a
    # provider-specific composite index for equality(runId)+order(seq) in
    # Firestore while preserving identical behavior on PostgreSQL/memory.
    rows = repository.query_documents(
        OP_COLLECTION,
        filters=[("runId", "==", run_id)],
        limit=None,
    )
    return sorted(rows, key=lambda row: int(row.get("seq") or 0), reverse=True)


def _operation_effect(repository: Repository, op: dict[str, Any]) -> str:
    """Return applied/not-applied/drifted for an operation.

    Pending operations are deliberately inspected rather than trusted: a
    process may have crashed after the data write but before the journal status
    flip. This makes rollback useful even for interrupted migrations.
    """
    collection = str(op.get("collection") or "")
    doc_id = str(op.get("docId") or "")
    current = repository.get_document(collection, doc_id)
    kind = op.get("kind")
    if kind == "create":
        if current is None:
            return "not-applied"
        return "applied" if current == op.get("after") else "drifted"
    if kind == "fields":
        if current is None:
            return "drifted"
        after = op.get("after") or {}
        before = op.get("before") or {}
        if all(_matches_field_state(current, field, state) for field, state in after.items()):
            return "applied"
        if all(_matches_field_state(current, field, state) for field, state in before.items()):
            return "not-applied"
        return "drifted"
    return "drifted"


def rollback_migration(repository: Repository, run_id: str) -> dict[str, int]:
    """Rollback one migration run after a full drift preflight.

    Nothing is mutated until every operation is proven to be either still in
    the migration's expected after-state or already absent/restored. This
    avoids partial rollback when an operator has legitimately edited a migrated
    resource since the run.
    """
    run = repository.get_document(RUN_COLLECTION, run_id)
    if run is None:
        raise ValueError(f"unknown tenant migration run {run_id!r}")
    if str(run.get("status") or "") == "rolled_back":
        return {"restored": 0, "deleted": 0, "already_restored": 0}

    operations = _operations(repository, run_id)
    states: list[tuple[dict[str, Any], str]] = []
    drifted: list[str] = []
    for op in operations:
        state = _operation_effect(repository, op)
        states.append((op, state))
        if state == "drifted":
            drifted.append(f"{op.get('collection')}/{op.get('docId')}")
    if drifted:
        raise ValueError(
            "rollback refused because migrated data changed after the run: " + ", ".join(drifted)
        )

    restored = 0
    deleted = 0
    already_restored = 0
    for op, state in states:
        if state == "not-applied":
            already_restored += 1
            continue
        collection = str(op["collection"])
        doc_id = str(op["docId"])
        if op["kind"] == "create":
            repository.delete_document(collection, doc_id)
            deleted += 1
            continue

        current = repository.get_document(collection, doc_id)
        assert current is not None
        restored_doc = dict(current)
        for field, before_state in (op.get("before") or {}).items():
            if before_state.get("present"):
                restored_doc[field] = before_state.get("value")
            else:
                restored_doc.pop(field, None)
        repository.set_document(collection, doc_id, restored_doc, merge=False)
        restored += 1

    repository.update_document(
        RUN_COLLECTION,
        run_id,
        {
            "status": "rolled_back",
            "rolledBackAt": _now(),
            "rollbackSummary": {
                "restored": restored,
                "deleted": deleted,
                "alreadyRestored": already_restored,
            },
        },
    )
    return {"restored": restored, "deleted": deleted, "already_restored": already_restored}


__all__ = [
    "MigrationJournal",
    "OP_COLLECTION",
    "RUN_COLLECTION",
    "rollback_migration",
]
