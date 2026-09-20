"""ChatSessionIndex — queryable metadata mirror for durable chat sessions.

Events and state live in the configured ADK SessionService.  This model is the
backend-neutral metadata row used to list, filter, share and rename sessions
without scanning the transcript store.

Access enforcement reuses the shared ``AccessControl`` evaluator, but tenant
isolation is a separate hard boundary: ``tenant_id`` is the stable scope key.
Legacy ``owner_domain`` remains only as a migration hint and MUST resolve
through the tenant directory before an old row may be exposed in a tenant
request.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from db.models.access import AccessControl


class ChatSessionIndex(BaseModel):
    """Repository document at ``chat_sessions/{sessionId}``.

    ``owner_id`` satisfies the ``_HasAccess`` protocol used by the ordinary
    sharing evaluator. ``tenant_id`` is intentionally independent of those
    sharing rules: public/domain/tagged access never grants cross-tenant access.
    """

    session_id: str = Field(alias="sessionId")

    # Stable Phase-3 tenant boundary. New rows always write this value from the
    # authenticated identity. Rows created before the field existed keep the
    # empty default and are handled fail-closed unless ownerDomain can be
    # resolved by TenantDirectory.
    tenant_id: str = Field(default="", alias="tenantId")

    # PROVISIONAL: pre-created by bootstrap before the first message. Hidden
    # from history until the first real turn clears it.
    provisional: bool = False
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")
    # ADK app/session namespace. Legacy rows stay on APP_NAME; Root Agent
    # rows use `root-agent` so their runtime identity is isolated.
    agent_id: str = Field(default="aitana_platform", alias="agentId")
    skill_id: str = Field(alias="skillId")
    skill_history: list[str] = Field(default_factory=list, alias="skillHistory")
    owner_uid: str = Field(alias="ownerUid")

    # Legacy/migration identity. Never use this as the primary tenant key.
    owner_domain: str = Field(default="", alias="ownerDomain")

    access_control: AccessControl = Field(alias="accessControl")
    title: str | None = None
    turn_count: int = Field(default=0, alias="turnCount")
    first_message_at: datetime = Field(alias="firstMessageAt")
    last_message_at: datetime = Field(alias="lastMessageAt")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    transcript_lost: bool = Field(default=False, alias="transcriptLost")

    model_config = ConfigDict(populate_by_name=True)

    @property
    def owner_id(self) -> str:
        return self.owner_uid


__all__ = ["ChatSessionIndex"]
