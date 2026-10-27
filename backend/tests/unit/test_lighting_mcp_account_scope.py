"""A personal deployment's business database must not become a shared MCP."""

from unittest.mock import MagicMock, patch

from auth.capability_access import authorized_root_config, mcp_call_allowed
from auth.models import User
from db.models.root_agent import RootAgentConfig


def test_server_account_restriction_applies_to_agent_and_direct_mcp_calls():
    config = RootAgentConfig(mcpServers=["lighting-query", "shared"])
    repository = MagicMock()
    repository.get_document.side_effect = lambda collection, ref: {
        "enabled": True,
        **({"allowedUserIds": ["owner"]} if ref == "lighting-query" else {}),
    }
    with (
        patch("auth.capability_access.refresh_authorization", side_effect=lambda user: user),
        patch("auth.capability_access.build_access_context"),
        patch("auth.capability_access.get_user_profile", return_value=MagicMock(skills=[], information="")),
        patch("auth.capability_access.get_repository", return_value=repository),
        patch("config.platform_config.get_platform_config", return_value=MagicMock(agent=config)),
    ):
        owner = User(uid="owner", email="owner@example.com")
        other = User(uid="other", email="other@example.com")
        assert authorized_root_config(config, owner).mcp_servers == ["lighting-query", "shared"]
        assert authorized_root_config(config, other).mcp_servers == ["shared"]
        assert mcp_call_allowed(owner, "lighting-query", "query_lighting")
        assert not mcp_call_allowed(other, "lighting-query", "query_lighting")
