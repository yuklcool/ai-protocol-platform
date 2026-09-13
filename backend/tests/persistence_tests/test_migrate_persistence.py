from db.repositories.memory import MemoryRepository
from scripts.migrate_persistence import migrate_collection


def test_migrate_collection_copies_ids_and_payloads():
    source = MemoryRepository()
    target = MemoryRepository()
    source.set_document("clients", "a.example", {"display_name": "A"})
    source.set_document("clients", "b.example", {"display_name": "B"})

    seen, written = migrate_collection(
        source,
        target,
        "clients",
        dry_run=False,
        batch_size=1,
    )

    assert (seen, written) == (2, 2)
    assert target.get_document("clients", "a.example")["display_name"] == "A"
    assert target.get_document("clients", "b.example")["display_name"] == "B"


def test_dry_run_does_not_write():
    source = MemoryRepository()
    target = MemoryRepository()
    source.set_document("skills", "skill-1", {"name": "Demo"})

    seen, written = migrate_collection(
        source,
        target,
        "skills",
        dry_run=True,
        batch_size=200,
    )

    assert (seen, written) == (1, 1)
    assert target.get_document("skills", "skill-1") is None
