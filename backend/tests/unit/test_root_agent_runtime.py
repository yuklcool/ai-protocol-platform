from unittest.mock import patch

import pytest

from agents.root_runtime import (
    RootCapabilityDenied,
    compose_root_skill,
    resolve_root_capability,
)
from auth import User
from auth.access_context import AccessContext
from db.models import SkillConfig, SkillMetadata
from db.models.root_agent import RootAgentConfig


def _user() -> User:
    return User(uid="user-1", email="user@example.com", domain="example.com", tenant_id="tenant-1")


def _access() -> AccessContext:
    return AccessContext(uid="user-1", email="user@example.com", domain="example.com", tenant_id="tenant-1")


def _skill(skill_id: str = "cap-a", slug: str = "cap-a") -> SkillConfig:
    return SkillConfig(
        name=slug,
        description="A capability.",
        instructions="Capability instructions.",
        skillId=skill_id,
        slug=slug,
        ownerId="owner-1",
        tenantId="tenant-1",
        accessControl={"type": "public"},
        skillMetadata=SkillMetadata(
            model="lite",
            tools=["alpha", "beta"],
            toolConfigs={"mcp": {"servers": ["mcp-a", "mcp-b"]}, "a2ui": {"enabled": True}},
        ),
    )


def test_resolver_loads_only_the_requested_capability():
    capability = _skill()
    config = RootAgentConfig(skills=["cap-a", "cap-b"])
    with (
        patch("agents.root_runtime.resolve_skill_ref", return_value=capability) as resolve,
    ):
        resolved = resolve_root_capability(config, _user(), _access(), "cap-a")

    assert resolved is capability
    resolve.assert_called_once_with("cap-a", "user-1")


def test_resolver_enforces_root_ceiling_and_tenant_filter():
    capability = _skill().model_copy(update={"tenant_id": "foreign"})
    with (
        patch("agents.root_runtime.resolve_skill_ref", return_value=capability),
    ):
        with pytest.raises(RootCapabilityDenied):
            resolve_root_capability(RootAgentConfig(skills=["cap-a"]), _user(), _access(), "cap-a")

    with pytest.raises(RootCapabilityDenied):
        resolve_root_capability(RootAgentConfig(skills=["cap-a"]), _user(), _access(), "cap-b")


def test_composition_applies_root_model_instruction_and_capability_ceilings():
    composed = compose_root_skill(
        _skill(),
        RootAgentConfig(
            model="smart",
            instructions="Root instructions.",
            skills=["cap-a"],
            tools=["alpha"],
            mcpServers=["mcp-a"],
            interaction={"a2uiEnabled": False},
        ),
    )

    assert composed.skill_metadata.model == "smart"
    assert composed.instructions == "Root instructions.\n\nCapability instructions."
    assert composed.skill_metadata.tools == ["alpha"]
    assert composed.skill_metadata.tool_configs["mcp"]["servers"] == ["mcp-a"]
    assert composed.skill_metadata.tool_configs["defaults"] == {"artifacts": False, "memory": False}
    assert composed.skill_metadata.tool_configs["a2ui"]["enabled"] is False


def test_empty_root_drops_skill_mcp_connections_and_context_write_grants():
    capability = _skill()
    capability.skill_metadata.tool_configs["mcp"]["allow_context_writes"] = ["mcp-a"]
    composed = compose_root_skill(capability, RootAgentConfig())
    assert composed.skill_metadata.tool_configs["mcp"] == {"servers": []}
    assert capability.skill_metadata.tool_configs["mcp"]["servers"] == ["mcp-a", "mcp-b"]


@pytest.mark.parametrize("model_name", ["CreateSkillRequest", "UpdateSkillRequest"])
@pytest.mark.parametrize("key", ["toolConfigs", "tool_configs"])
def test_skill_write_rejects_obsolete_mcp_configuration(model_name, key):
    from pydantic import ValidationError

    from skills import routes

    model = getattr(routes, model_name)
    with pytest.raises(ValidationError, match="Skill 不再配置 MCP"):
        model.model_validate({"name": "example", "skillMetadata": {key: {"mcp": {"servers": []}}}})


def test_persistence_rejects_skill_mcp_before_writing():
    from skills import skill_config

    with patch("skills.skill_config.fs.set_document") as write:
        with pytest.raises(ValueError, match="Skill 不再配置 MCP"):
            skill_config.create_skill(
                name="example", description="Example skill", skillMetadata={"toolConfigs": {"mcp": {"servers": []}}}
            )
        write.assert_not_called()
    capability = _skill()
    capability.skill_metadata.tool_configs.pop("mcp")
    with (
        patch("skills.skill_config.get_skill", return_value=capability),
        patch("skills.skill_config.fs.update_document") as write,
    ):
        with pytest.raises(ValueError, match="Skill 不再配置 MCP"):
            skill_config.update_skill(capability.skill_id, {"skillMetadata": {"toolConfigs": {"mcp": {"servers": []}}}})
        write.assert_not_called()


def test_current_skill_slug_is_resolved_before_checking_the_authorized_id():
    capability = _skill(skill_id="stable-id", slug="capability")
    with patch("agents.root_runtime.resolve_skill_ref", return_value=capability):
        assert (
            resolve_root_capability(RootAgentConfig(skills=["stable-id"]), _user(), _access(), "capability")
            is capability
        )
        with pytest.raises(RootCapabilityDenied):
            resolve_root_capability(RootAgentConfig(skills=["other-id"]), _user(), _access(), "capability")
        with pytest.raises(RootCapabilityDenied):
            resolve_root_capability(RootAgentConfig(), _user(), _access(), "capability")
