"""User-owned bindings must not widen shared Agent privileges."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from google.adk.sessions import InMemorySessionService
from pydantic import ValidationError

from adk.user_session_service import UserScopedSessionService
from agents.capabilities import root_capability_tool
from agents.root_runtime import compose_root_skill, root_agent_skill
from auth.access_context import build_access_context
from auth.capability_access import authorized_root_config
from auth.models import User
from db.models import SkillConfig
from db.models.root_agent import RootAgentConfig
from db.persistence import get_repository, reset_repository_for_testing
from db.repositories.memory import MemoryRepository
from db.user_profiles import UserProfile, get_user_profile, save_user_profile
from observability.user_context import get_resource_user_id, get_user_context, set_user_context


@pytest.fixture
def identities(monkeypatch):
    reset_repository_for_testing(MemoryRepository())
    alice, bob = User(uid="alice", auth_mode="stub"), User(uid="bob", auth_mode="stub")
    shared = SkillConfig(skillId="shared", name="shared", ownerId="aitana-platform", accessControl={"type": "public"})
    private = SkillConfig(skillId="personal", name="personal", instructions="PERSONAL-INSTRUCTIONS", ownerId=alice.uid)
    skills = {skill.skill_id: skill for skill in (shared, private)}
    monkeypatch.setattr("skills.skill_config.get_skill", skills.get)
    monkeypatch.setattr("agents.root_runtime.resolve_skill_ref", lambda ref, uid=None: skills.get(ref))
    return alice, bob


def test_shared_and_personal_catalogs_are_independent(identities, monkeypatch):
    alice, bob = identities
    save_user_profile(alice.uid, UserProfile(skills=["personal"], information="ALICE-ONLY"))
    root = RootAgentConfig(skills=["shared"], tools=["read_attached_document"], model="smart")
    monkeypatch.setattr("agents.capabilities.get_platform_config", lambda: SimpleNamespace(agent=root))
    a, b = authorized_root_config(root, alice), authorized_root_config(root, bob)
    assert a.skills == ["shared", "personal"] and b.skills == ["shared"]
    assert "ALICE-ONLY" in a.instructions and "ALICE-ONLY" not in b.instructions
    assert "personal" in root_capability_tool(alice, build_access_context(alice))[1]
    assert "personal" not in root_capability_tool(bob, build_access_context(bob))[1]
    assert root.skills == ["shared"] and root.instructions == ""


def test_private_binding_rejects_foreign_owner_and_privilege_fields(identities):
    _alice, bob = identities
    with pytest.raises(HTTPException):
        save_user_profile(bob.uid, UserProfile(skills=["personal"]))
    with pytest.raises(ValidationError):
        UserProfile.model_validate({"skills": [], "tools": ["dangerous"], "mcpServers": ["secret"], "model": "other"})
    assert get_user_profile(bob.uid).skills == []
    get_repository().set_document("user_profiles", bob.uid, {"skills": ["personal"]})
    assert authorized_root_config(RootAgentConfig(), bob).skills == []


def test_private_profile_revocation_changes_policy_immediately(identities):
    alice, _ = identities
    save_user_profile(alice.uid, UserProfile(skills=["personal"], information="first"))
    root = RootAgentConfig()
    first = authorized_root_config(root, alice)
    save_user_profile(alice.uid, UserProfile(information="second"))
    second = authorized_root_config(root, alice)
    assert first.skills == ["personal"] and second.skills == []
    assert first.model_dump_json() != second.model_dump_json()
    assert "first" not in second.instructions


def test_personal_skill_cannot_replace_root_tools_or_model(identities):
    root = RootAgentConfig(model="smart", tools=["read_attached_document"], mcpServers=["shared-mcp"])
    skill = root_agent_skill(root)
    skill.skill_metadata.tools = ["dangerous"]
    skill.skill_metadata.model = "other"
    skill.skill_metadata.tool_configs = {"mcp": {"servers": ["private-server"]}}
    composed = compose_root_skill(skill, root)
    assert composed.skill_metadata.model == "smart"
    assert composed.skill_metadata.tools == ["read_attached_document"]
    assert composed.skill_metadata.tool_configs["mcp"] == {"servers": ["shared-mcp"]}


def test_untrusted_metadata_cannot_change_user_or_resource_owner(identities):
    alice, _ = identities
    set_user_context(alice, {"user.id": "bob", "resource.user_id": "bob", "trace.test": "yes"})
    assert get_user_context()["user.id"] == get_resource_user_id() == "alice"


@pytest.mark.asyncio
async def test_user_app_state_and_sessions_are_isolated(identities):
    alice, bob = identities
    service = UserScopedSessionService(InMemorySessionService())
    set_user_context(alice)
    await service.create_session(
        app_name="root-agent", user_id=alice.uid, session_id="same", state={"app:private": "ALICE"}
    )
    set_user_context(bob)
    other = await service.create_session(app_name="root-agent", user_id=bob.uid, session_id="same")
    assert "app:private" not in other.state
    with pytest.raises(PermissionError):
        await service.get_session(app_name="root-agent", user_id=alice.uid, session_id="same")
    set_user_context(alice)
    restored = await service.get_session(app_name="root-agent", user_id=alice.uid, session_id="same")
    assert restored.state["app:private"] == "ALICE"


@pytest.mark.asyncio
async def test_artifact_storage_rejects_another_users_identity(identities):
    from google.adk.artifacts import InMemoryArtifactService
    from google.genai import types

    from adk.user_artifact_service import UserScopedArtifactService

    alice, bob = identities
    service = UserScopedArtifactService(InMemoryArtifactService())
    set_user_context(alice)
    await service.save_artifact(
        app_name="root-agent",
        user_id=alice.uid,
        session_id="same",
        filename="secret.txt",
        artifact=types.Part.from_text(text="ALICE-ONLY"),
    )
    set_user_context(bob)
    with pytest.raises(PermissionError):
        await service.load_artifact(app_name="root-agent", user_id=alice.uid, session_id="same", filename="secret.txt")
    assert (
        await service.load_artifact(app_name="root-agent", user_id=bob.uid, session_id="same", filename="secret.txt")
        is None
    )


@pytest.mark.asyncio
async def test_memory_recall_requires_the_verified_owner(identities):
    from google.adk.events import Event
    from google.adk.sessions import Session
    from google.genai import types

    from adk.postgres_memory import PostgresMemoryService
    from db.repositories.memory import MemoryRepository

    alice, bob = identities
    service = PostgresMemoryService(repository=MemoryRepository(), require_user=True)
    set_user_context(alice)
    await service.add_session_to_memory(
        Session(
            id="same",
            app_name="root-agent",
            user_id=alice.uid,
            events=[
                Event(
                    author="user", content=types.Content(role="user", parts=[types.Part.from_text(text="ALICE-ONLY")])
                )
            ],
        )
    )
    set_user_context(bob)
    with pytest.raises(PermissionError):
        await service.search_memory(app_name="root-agent", user_id=alice.uid, query="ALICE-ONLY")
    assert not (await service.search_memory(app_name="root-agent", user_id=bob.uid, query="ALICE-ONLY")).memories


def test_native_tool_revocation_is_checked_during_an_existing_run(identities, monkeypatch):
    from adk.callbacks import make_permission_enforcer
    from auth.permissions import ToolPermissionDenied

    root = RootAgentConfig(tools=["shared_tool"])
    monkeypatch.setattr("config.platform_config.get_platform_config", lambda: SimpleNamespace(agent=root))
    alice, _ = identities
    callback = make_permission_enforcer("", "", user=alice, root_agent=True)
    tool = SimpleNamespace(name="shared_tool")
    context = SimpleNamespace(agent_name="root-agent", state={})
    assert callback(tool, {}, context) is None
    root.tools = []
    with pytest.raises(ToolPermissionDenied):
        callback(tool, {}, context)


@pytest.mark.asyncio
async def test_root_interaction_and_attachment_tools_have_explicit_server_grants(identities, monkeypatch):
    from google.adk.tools import FunctionTool

    from adk.a2ui import make_a2ui_toolset
    from adk.callbacks import make_permission_enforcer
    from adk.elicitation import request_confirmation
    from auth.permissions import ToolPermissionDenied
    from tools.documents.access import read_attached_document

    alice, _ = identities
    root = RootAgentConfig()
    monkeypatch.setattr("config.platform_config.get_platform_config", lambda: SimpleNamespace(agent=root))
    callback = make_permission_enforcer("", "", user=alice, root_agent=True)
    context = SimpleNamespace(agent_name="root-agent", state={})
    surface_tool = (await make_a2ui_toolset().get_tools(context))[0]
    confirmation = FunctionTool(request_confirmation)
    assert callback(surface_tool, {}, context) is None
    assert callback(confirmation, {}, context) is None
    root.interaction.a2ui_enabled = False
    with pytest.raises(ToolPermissionDenied):
        callback(surface_tool, {}, context)
    with pytest.raises(ToolPermissionDenied):
        callback(confirmation, {}, context)
    reader = FunctionTool(read_attached_document)
    with pytest.raises(ToolPermissionDenied):
        callback(reader, {}, context)
    context.state["document_ids"] = ["owned"]
    get_repository().set_document(
        "parsed_documents", "owned", {"userId": alice.uid, "parseStatus": "parsed", "blocks": [{"text": "owned"}]}
    )
    assert callback(reader, {"doc_id": "owned"}, context) is None


@pytest.mark.parametrize("binding", ["google_search", "ai_search", "code_execution"])
def test_model_aware_tools_use_the_current_agent_binding(identities, monkeypatch, binding):
    from adk.callbacks import make_permission_enforcer
    from auth.permissions import ToolPermissionDenied

    alice, _ = identities
    root = RootAgentConfig(tools=[binding])
    monkeypatch.setattr("config.platform_config.get_platform_config", lambda: SimpleNamespace(agent=root))
    tool = SimpleNamespace(name="sdk_delegate", _aitana_root_binding=binding)
    context = SimpleNamespace(agent_name="root-agent", state={})
    callback = make_permission_enforcer("", "", user=alice, root_agent=True)
    assert callback(tool, {}, context) is None
    root.tools = []
    with pytest.raises(ToolPermissionDenied):
        callback(tool, {}, context)
