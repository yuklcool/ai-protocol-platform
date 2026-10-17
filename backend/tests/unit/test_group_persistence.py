"""Anonymous-group codes must survive a container restart (v6.19.0, AIPLA #16).

Group state used to live only in one process's memory, so a Cloud Run instance
being recycled — or a request simply landing on a *different* instance — made a
live code stop working. That forces every deployment to `min-instances=1`,
which defeats running serverless at all. The reporting fork pinned an instance
to work around it.

The scenario these tests model is the one that actually broke: **a cold
instance that has never seen the code**. `_state.reset_for_tests()` is exactly
that — a fresh process with an empty cache and a warm Firestore behind it.
"""

from __future__ import annotations

import pytest

from auth import group_id_auth as gia
from auth.group_id_auth import (
    AnonymousGroupAuth,
    GroupNotFound,
    GroupPersistenceError,
    create_group,
    delete_group,
    get_group,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    """Exercise the repository contract with an isolated durable test store."""
    from db.persistence import reset_repository_for_testing
    from db.repositories.memory import MemoryRepository

    monkeypatch.setenv("GROUP_AUTH_SIGNING_SECRET", "test-secret-not-a-real-one")
    reset_repository_for_testing(MemoryRepository())

    AnonymousGroupAuth.reset_for_tests()
    yield
    AnonymousGroupAuth.reset_for_tests()


def _simulate_restart() -> None:
    """Drop all in-process state, keeping Firestore. A cold instance."""
    AnonymousGroupAuth.reset_for_tests()


class TestSurvivesRestart:
    def test_code_still_resolves_after_a_restart(self):
        """THE bug: this returned None before, so the code stopped working."""
        record = create_group(title="Y9 Physics", skill_ids=["s1"], creator_uid="teacher-1")

        _simulate_restart()

        recovered = get_group(record.group_id)
        assert recovered is not None, "group vanished on restart — min-instances=1 all over again"
        assert recovered.group_id == record.group_id

    def test_recovered_record_round_trips_every_field(self):
        """A half-restored group is worse than none — it fails later, elsewhere."""
        record = create_group(
            title="Y9 Physics",
            skill_ids=["s1", "s2"],
            creator_uid="teacher-1",
            ttl_days=7,
            max_concurrent_sessions=42,
        )

        _simulate_restart()
        recovered = get_group(record.group_id)

        assert recovered == record

    def test_lookup_rehydrates_the_cache(self):
        """The Firestore read is a fallback, not the steady state."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")
        _simulate_restart()
        assert record.group_id not in gia._state.groups

        get_group(record.group_id)

        assert record.group_id in gia._state.groups

    def test_revocation_survives_a_restart(self):
        """A revoked code must stay dead even on an instance that never saw it."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")
        delete_group(record.group_id, requesting_uid="teacher-1")

        _simulate_restart()

        assert get_group(record.group_id) is None

    def test_creator_can_revoke_a_code_minted_before_a_restart(self):
        """Revocation is most needed exactly when the minting instance is gone."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")
        _simulate_restart()

        delete_group(record.group_id, requesting_uid="teacher-1")

        assert get_group(record.group_id) is None

    def test_ownership_still_enforced_after_a_restart(self):
        """The creator gate must not weaken just because the record was reloaded."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")
        _simulate_restart()

        with pytest.raises(PermissionError):
            delete_group(record.group_id, requesting_uid="someone-else")


class TestUnknownGroups:
    def test_unknown_code_is_still_none(self):
        assert get_group("NOPE-NOPE") is None

    def test_revoking_an_unknown_code_raises(self):
        with pytest.raises(GroupNotFound):
            delete_group("NOPE-NOPE", requesting_uid="teacher-1")


class TestFailureModes:
    def test_create_fails_loud_when_the_durable_write_fails(self, monkeypatch):
        """Deliberate deviation from the fork's best-effort write.

        Returning a code we could not persist is a silent promise-break: it
        works in the demo and dies at the next deploy, with nothing telling
        the user. Fail at mint time instead.
        """
        from auth import group_id_auth as storage

        monkeypatch.setattr(
            storage, "set_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("firestore down"))
        )

        with pytest.raises(GroupPersistenceError, match="would stop working"):
            create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")

    def test_failed_create_leaves_no_phantom_in_cache(self, monkeypatch):
        """A code that was never persisted must not work on this instance either."""
        from auth import group_id_auth as storage

        monkeypatch.setattr(
            storage, "set_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("firestore down"))
        )

        with pytest.raises(GroupPersistenceError):
            create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")

        assert gia._state.groups == {}

    def test_read_failure_degrades_to_not_found(self, monkeypatch):
        """A Firestore blip must not 500 an auth lookup — deny is the safe way."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")
        _simulate_restart()

        from auth import group_id_auth as storage

        monkeypatch.setattr(
            storage, "get_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("firestore down"))
        )

        assert get_group(record.group_id) is None

    def test_revoke_tolerates_a_write_failure(self, monkeypatch):
        """In-memory state is already correct; don't fail the caller's request."""
        record = create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")

        from auth import group_id_auth as storage

        monkeypatch.setattr(storage, "update_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))

        delete_group(record.group_id, requesting_uid="teacher-1")  # must not raise
        assert get_group(record.group_id) is None


def test_persist_uses_merge_so_external_fields_are_not_clobbered(monkeypatch):
    """Another script may own keys on this doc; a full overwrite drops them."""
    seen: dict = {}

    from auth import group_id_auth as storage

    def _capture(collection, doc_id, data, merge=False):
        seen.update({"collection": collection, "merge": merge})

    monkeypatch.setattr(storage, "set_document", _capture)
    create_group(title="T", skill_ids=["s1"], creator_uid="teacher-1")

    assert seen["collection"] == "anon_groups"
    assert seen["merge"] is True
