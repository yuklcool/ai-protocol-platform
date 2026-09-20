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
        patch("agents.root_runtime.resolve_enabled_skills", return_value=None),
    ):
        resolved = resolve_root_capability(config, _user(), _access(), "cap-a")

    assert resolved is capability
    resolve.assert_called_once_with("cap-a", "user-1")


def test_resolver_enforces_root_ceiling_and_tenant_filter():
    capability = _skill()
    with (
        patch("agents.root_runtime.resolve_skill_ref", return_value=capability),
        patch("agents.root_runtime.resolve_enabled_skills", return_value=["other-capability"]),
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
