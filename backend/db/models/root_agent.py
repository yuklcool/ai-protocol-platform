"""Single Root Agent configuration contract.

The platform exposes one user-facing agent. Skills, native tools, MCP servers
and knowledge sources are capabilities resolved by that agent at runtime. The
model is intentionally additive so the existing SkillConfig API can remain
the compatibility path while the runtime migration is in progress.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RootAgentInteraction(BaseModel):
    """Agent-level interaction settings, kept out of ordinary Skills."""

    a2ui_enabled: bool = Field(default=True, alias="a2uiEnabled")
    default_surface: str = Field(default="chat", alias="defaultSurface")
    default_update_mode: Literal["replace", "patch"] = Field(default="replace", alias="defaultUpdateMode")
    allow_surface_context_writes: bool = Field(default=False, alias="allowSurfaceContextWrites")
    allow_action_triggered_runs: bool = Field(default=False, alias="allowActionTriggeredRuns")
    welcome_message: str = Field(default="", alias="welcomeMessage", max_length=2000)
    voice_enabled: bool = Field(default=False, alias="voiceEnabled")

    model_config = {"populate_by_name": True}


class RootAgentTenantOverride(BaseModel):
    """Tenant-scoped Root Agent policy overlay.

    The platform singleton remains the global ceiling/default, while this
    optional map lets a tenant bind its own private Skills and model policy
    without placing tenant-owned resource ids in a global allow-list.
    ``None`` means "inherit the platform value"; an empty list intentionally
    means "allow none".
    """

    model: str | None = None
    instructions: str | None = None
    skills: list[str] | None = None
    tools: list[str] | None = None
    mcp_servers: list[str] | None = Field(default=None, alias="mcpServers")
    knowledge: list[str] | None = None
    interaction: RootAgentInteraction | None = None
    permissions: dict[str, Any] | None = None
    specialist_agents: list[str] | None = Field(default=None, alias="specialistAgents")

    model_config = {"populate_by_name": True}


class RootAgentConfig(BaseModel):
    """The one platform Agent and its capability bindings.

    Lists contain stable resource ids. Effective access is still evaluated by
    the backend; saving an id here never grants a user or tenant access by
    itself. Unknown legacy fields are ignored so older platform-config docs
    remain readable during migration.
    """

    display_name: str = Field(default="Root Agent", alias="displayName", max_length=120)
    description: str = Field(
        default="The platform's single user-facing AI assistant.",
        max_length=1000,
    )
    model: str = "smart"
    instructions: str = Field(default="", max_length=20000)
    skills: list[str] = Field(default_factory=list, max_length=200)
    tools: list[str] = Field(default_factory=list, max_length=200)
    mcp_servers: list[str] = Field(default_factory=list, alias="mcpServers", max_length=100)
    knowledge: list[str] = Field(default_factory=list, max_length=100)
    interaction: RootAgentInteraction = Field(default_factory=RootAgentInteraction)
    permissions: dict[str, Any] = Field(default_factory=dict)
    specialist_agents: list[str] = Field(default_factory=list, alias="specialistAgents", max_length=100)
    tenant_overrides: dict[str, RootAgentTenantOverride] = Field(
        default_factory=dict,
        alias="tenantOverrides",
        max_length=100,
    )

    model_config = {"populate_by_name": True}


__all__ = ["RootAgentConfig", "RootAgentInteraction", "RootAgentTenantOverride"]
