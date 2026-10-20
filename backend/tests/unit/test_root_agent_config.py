from db.models import PlatformConfig, RootAgentConfig


def test_platform_config_has_one_root_agent_by_default() -> None:
    config = PlatformConfig()
    assert config.agent.display_name == "Root Agent"
    assert config.agent.model == "smart"
    assert config.agent.skills == []


def test_root_agent_uses_camel_case_wire_fields() -> None:
    config = RootAgentConfig(displayName="Lighting Assistant", mcpServers=["lighting-mcp"])
    payload = config.model_dump(by_alias=True)
    assert payload["displayName"] == "Lighting Assistant"
    assert payload["mcpServers"] == ["lighting-mcp"]
