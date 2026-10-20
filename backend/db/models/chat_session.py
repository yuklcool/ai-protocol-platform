from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from db.models.access import AccessControl


class ChatSessionIndex(BaseModel):
    session_id: str = Field(alias="sessionId")

    # authenticated identity. Rows created before the field existed keep the
    # empty default and are handled fail-closed unless ownerDomain can be

    # PROVISIONAL: pre-created by bootstrap before the first message. Hidden
    # from history until the first real turn clears it.
    provisional: bool = False
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")
    document_tabs: list[dict] = Field(default_factory=list, alias="documentTabs")
    # ADK app/session namespace. Legacy rows stay on APP_NAME; Root Agent
    # rows use `root-agent` so their runtime identity is isolated.
    agent_id: str = Field(default="aitana_platform", alias="agentId")
    # Persist the namespace independently from the mutable capability/agent
    # label. A session may change capabilities during its lifetime; changing
    # this value would make the transcript appear to disappear from ADK.
    app_name: str = Field(default="aitana_platform", alias="appName")
    skill_id: str = Field(alias="skillId")
    skill_history: list[str] = Field(default_factory=list, alias="skillHistory")
    owner_uid: str = Field(alias="ownerUid")

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
