"""Phase 3 MCP registry tenant-isolation regressions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from auth import User
from observability.tenant_context import clear_tenant_enrichers, set_tenant_context
from tools.mcp import registry
from tools.mcp.tenant_scope import mcp_config_visible_to_tenant


def _bind(tenant_id: str) -> None:
    set_tenant_context(
        User(
            uid="same-uid",
            email="same@example.com",
            domain="legacy.example",
            tenant_id=tenant_id,
        )
    )


@pytest.fixture(autouse=True)
def _reset():
    registry.clear_registry_cache()
    clear_tenant_enrichers()
    _bind("tenant-a")
    yield
    registry.clear_registry_cache()
    clear_tenant_enrichers()


def _config(*, scope: str, tenant_id: str = "", url: str = "https://mcp.example.com") -> dict:
    data = {
        "name": "test",
        "scope": scope,
        "transport": "http",
        "url": url,
        "headers": {},
    }
    if tenant_id:
        data["tenantId"] = tenant_id
    return data


def test_platform_scope_is_explicitly_shared() -> None:
    config = _config(scope="platform")
    assert mcp_config_visible_to_tenant(config, "tenant-a") is True
    assert mcp_config_visible_to_tenant(config, "tenant-b") is True


def test_tenant_scope_requires_exact_stable_tenant() -> None:
    config = _config(scope="tenant", tenant_id="tenant-a")
    assert mcp_config_visible_to_tenant(config, "tenant-a") is True
    assert mcp_config_visible_to_tenant(config, "tenant-b") is False
    assert mcp_config_visible_to_tenant(config, "") is False


def test_historical_unscoped_config_fails_closed() -> None:
    assert mcp_config_visible_to_tenant({"url": "https://legacy.example.com"}, "tenant-a") is False


def test_registry_rejects_foreign_tenant_config() -> None:
    foreign = _config(scope="tenant", tenant_id="tenant-b")
    with patch("tools.mcp.registry.get_document", return_value=foreign):
        resolved, missing = registry.get_mcp_tools_with_status(["private-server"])
    assert resolved == []
    assert missing == ["private-server"]


def test_registry_cache_is_partitioned_by_tenant() -> None:
    calls: list[str] = []

    def fake_get(_collection: str, _server_id: str):
        from observability.tenant_context import get_current_tenant_id

        tenant = get_current_tenant_id()
        calls.append(tenant)
        return _config(
            scope="tenant",
            tenant_id=tenant,
            url=f"https://{tenant}.example.com/mcp",
        )

    with patch("tools.mcp.registry.get_document", side_effect=fake_get):
        _bind("tenant-a")
        first, missing_a = registry.get_mcp_tools_with_status(["shared-id"])
        _bind("tenant-b")
        second, missing_b = registry.get_mcp_tools_with_status(["shared-id"])
        # Re-enter tenant A: this must hit A's own cache entry, not B's.
        _bind("tenant-a")
        third, missing_a2 = registry.get_mcp_tools_with_status(["shared-id"])

    assert not missing_a and not missing_b and not missing_a2
    assert first[0]._connection_params.url == "https://tenant-a.example.com/mcp"
    assert second[0]._connection_params.url == "https://tenant-b.example.com/mcp"
    assert third[0]._connection_params.url == "https://tenant-a.example.com/mcp"
    assert calls == ["tenant-a", "tenant-b"]


def test_registry_without_tenant_context_fails_closed() -> None:
    set_tenant_context(User(uid="u", email="", domain="", tenant_id=""))
    with patch("tools.mcp.registry.get_document") as read:
        resolved, missing = registry.get_mcp_tools_with_status(["server"])
    assert resolved == []
    assert missing == ["server"]
    read.assert_not_called()
