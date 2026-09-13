"""Backend-neutral persistence contract tests.

The backend-wide conftest intentionally replaces ``db.firestore._client`` with
a MagicMock to prevent accidental GCP calls. Repository contract tests inject a
real InMemoryFirestoreClient explicitly so they exercise repository behavior.
"""

from db.firestore_inmemory import InMemoryFirestoreClient
from db.repositories.memory import MemoryRepository


def _memory_repo() -> MemoryRepository:
    return MemoryRepository(client=InMemoryFirestoreClient())


def test_memory_repository_crud_and_merge():
    repo = _memory_repo()
    repo.set_document("skills", "s1", {"name": "A", "count": 1})
    assert repo.get_document("skills", "s1") == {"name": "A", "count": 1}

    repo.set_document("skills", "s1", {"description": "B"}, merge=True)
    assert repo.get_document("skills", "s1") == {
        "name": "A",
        "count": 1,
        "description": "B",
    }

    repo.update_document("skills", "s1", {"name": "Updated"})
    assert repo.get_document("skills", "s1")["name"] == "Updated"

    repo.delete_document("skills", "s1")
    assert repo.get_document("skills", "s1") is None


def test_memory_repository_query_semantics():
    repo = _memory_repo()
    repo.set_document("skills", "a", {"ownerId": "u1", "score": 2, "tags": ["demo"]})
    repo.set_document("skills", "b", {"ownerId": "u1", "score": 5, "tags": ["prod"]})
    repo.set_document("skills", "c", {"ownerId": "u2", "score": 9, "tags": ["demo", "prod"]})

    docs = repo.query_documents(
        "skills",
        filters=[("ownerId", "==", "u1")],
        order_by="score",
        order_direction="DESCENDING",
        limit=1,
    )
    assert [doc["__id"] for doc in docs] == ["b"]

    demo = repo.query_documents("skills", filters=[("tags", "array_contains", "demo")])
    assert {doc["__id"] for doc in demo} == {"a", "c"}


def test_memory_repository_increment_is_numeric_and_atomic_at_contract_level():
    repo = _memory_repo()
    repo.set_document("usage", "x", {"count": 3})
    repo.increment_field("usage", "x", "count", 4)
    assert repo.get_document("usage", "x")["count"] == 7


def test_memory_repository_array_union_is_unique_and_preserves_existing_order():
    repo = _memory_repo()
    repo.set_document("sessions", "s1", {"documentIds": ["a", "b"]})
    repo.array_union_field("sessions", "s1", "documentIds", ["b", "c", "d", "c"])
    assert repo.get_document("sessions", "s1")["documentIds"] == ["a", "b", "c", "d"]


def test_memory_repository_array_union_rejects_non_array_field():
    repo = _memory_repo()
    repo.set_document("sessions", "s1", {"documentIds": "not-a-list"})
    try:
        repo.array_union_field("sessions", "s1", "documentIds", ["x"])
    except TypeError as exc:
        assert "not an array" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("array_union_field should reject non-list fields")


def test_memory_repository_healthcheck():
    assert _memory_repo().healthcheck() is True
