from __future__ import annotations

import pytest

from db.firestore_inmemory import InMemoryFirestoreClient
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from tools.mcp import registry


@pytest.fixture()
def repository():
    repo = MemoryRepository(InMemoryFirestoreClient())
    reset_repository_for_testing(repo)
    registry.clear_registry_cache()
    yield repo
    registry.clear_registry_cache()
    reset_repository_for_testing(None)


def test_mcp_registry_reads_server_config_from_repository(repository: MemoryRepository) -> None:
    repository.set_document(
        "mcp_servers",
        "internal-tools",
        {
            "scope": "platform",
            "url": "http://127.0.0.1:9000/mcp",
            "transport": "http",
            "headers": {},
            "name": "Internal tools",
        },
    )

    config = registry._cached_server_config("internal-tools")
    assert config is not None
    assert config["url"] == "http://127.0.0.1:9000/mcp"
    assert config["name"] == "Internal tools"


def test_mcp_registry_resolves_toolset_without_firestore(repository: MemoryRepository) -> None:
    repository.set_document(
        "mcp_servers",
        "internal-tools",
        {
            "scope": "platform",
            "url": "http://127.0.0.1:9000/mcp",
            "transport": "http",
            "headers": {},
            "name": "Internal tools",
        },
    )

    toolsets, missing = registry.get_mcp_tools_with_status(["internal-tools"])

    assert missing == []
    assert len(toolsets) == 1
    assert isinstance(toolsets[0], registry.TaggedMcpToolset)
    assert toolsets[0].aitana_server_id == "internal-tools"


def test_mcp_registry_missing_server_is_backend_neutral(repository: MemoryRepository) -> None:
    toolsets, missing = registry.get_mcp_tools_with_status(["does-not-exist"])
    assert toolsets == []
    assert missing == ["does-not-exist"]


def test_mcp_registry_cache_avoids_repeated_repository_reads(repository: MemoryRepository, monkeypatch):
    repository.set_document(
        "mcp_servers",
        "cached-tools",
        {
            "scope": "platform",
            "url": "http://127.0.0.1:9001/mcp",
            "transport": "http",
            "headers": {},
        },
    )

    calls = 0
    original = registry.get_document

    def counted_get_document(collection: str, doc_id: str):
        nonlocal calls
        calls += 1
        return original(collection, doc_id)

    monkeypatch.setattr(registry, "get_document", counted_get_document)

    first = registry._cached_server_config("cached-tools")
    second = registry._cached_server_config("cached-tools")

    assert first == second
    assert calls == 1


@pytest.fixture(autouse=True)
def _verified_mcp_tenant():
    from auth import User
    from observability.tenant_context import set_tenant_context
    from tools.mcp.registry import clear_registry_cache

    set_tenant_context(User(uid="viewer", tenant_id="tenant-a"))
    clear_registry_cache()
    yield
    clear_registry_cache()
    set_tenant_context(User(uid=""))
