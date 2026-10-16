"""Channel identity behavior through the backend-neutral repository contract."""

from unittest.mock import patch

import pytest

from channels import identity
from channels.identity import COLLECTION, IdentityResolver
from db.firestore_inmemory import InMemoryFirestoreClient
from db.repositories.memory import MemoryRepository


@pytest.fixture
def repository():
    repo = MemoryRepository(client=InMemoryFirestoreClient())
    with patch("db.persistence.get_repository", return_value=repo):
        yield repo


def test_identity_key_stays_compatible():
    assert identity._doc_id("discord", "12345") == "discord_12345"
    with pytest.raises(ValueError, match="contains '/'"):
        identity._doc_id("email", "bad/value")


@pytest.mark.asyncio
async def test_existing_mapping_resolves_and_touches_last_seen(repository):
    repository.set_document(COLLECTION, "telegram_999", {"firebase_uid": "known", "last_seen_at": "old"})
    assert await IdentityResolver.resolve("telegram", "999") == "known"
    assert repository.get_document(COLLECTION, "telegram_999")["last_seen_at"] != "old"


@pytest.mark.asyncio
async def test_missing_and_malformed_mapping_do_not_grant_identity(repository):
    assert await IdentityResolver.resolve("discord", "missing") is None
    repository.set_document(COLLECTION, "discord_123", {"channel": "discord"})
    assert await IdentityResolver.resolve("discord", "123") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("email,domain", [(None, ""), ("user@example.com", "example.com")])
async def test_create_persists_and_can_be_resolved_after_reconstruction(repository, email, domain):
    uid = await IdentityResolver.auto_create("telegram", "42", email=email)
    assert uid == "channel-telegram_42"
    record = repository.get_document(COLLECTION, "telegram_42")
    assert record["domain"] == domain
    assert record["email"] == (email or "")
    assert record["group_tags"] == []
    assert record["created_at"] and record["last_seen_at"]
    assert await IdentityResolver().resolve("telegram", "42") == uid
