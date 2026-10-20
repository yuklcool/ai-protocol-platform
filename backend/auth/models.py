"""Provider-neutral, verified user identity."""

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    model_config = ConfigDict(frozen=True)
    uid: str
    email: str = ""
    domain: str = ""
    group_tags: frozenset[str] = Field(default_factory=frozenset)
    auth_mode: str = "firebase"
    group_id: str = ""


__all__ = ["User"]
