"""Personal instructions and owned Skill bindings, keyed by verified user ID."""

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from db.persistence import get_repository

COLLECTION = "user_profiles"


class UserProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    skills: list[str] = Field(default_factory=list, max_length=200)
    information: str = Field(default="", max_length=20000)


def get_user_profile(uid: str) -> UserProfile:
    if not uid.strip():
        raise PermissionError("Authenticated user required")
    row = get_repository().get_document(COLLECTION, uid) or {}
    return UserProfile.model_validate({key: row[key] for key in ("skills", "information") if key in row})


def save_user_profile(uid: str, profile: UserProfile) -> UserProfile:
    from skills.skill_config import get_skill

    if not uid.strip():
        raise PermissionError("Authenticated user required")
    refs = list(dict.fromkeys(profile.skills))
    for ref in refs:
        skill = get_skill(ref)
        if skill is None or skill.owner_id != uid:
            raise HTTPException(422, "Personal Skills must be owned by this user")
    result = profile.model_copy(update={"skills": refs})
    get_repository().set_document(COLLECTION, uid, result.model_dump(), merge=True)
    return result
