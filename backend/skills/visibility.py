"""Skill catalog visibility follows resource ownership and explicit sharing."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillVisibility:
    skill_id: str
    slug: str
    label: str
    access_allowed: bool
    access_reason: str

    @property
    def visible(self) -> bool:
        return self.access_allowed

    @property
    def reason(self) -> str:
        return self.access_reason


def evaluate_visibility(configs: list[Any], access: Any) -> list[SkillVisibility]:
    return [
        SkillVisibility(
            str(cfg.skill_id),
            cfg.slug or "",
            cfg.display_name or cfg.name,
            access.can_access_skill(cfg),
            f"Resource ACL: {cfg.access_control.type}",
        )
        for cfg in configs
    ]


def visible_configs(configs: list[Any], access: Any) -> list[Any]:
    return [cfg for cfg in configs if access.can_access_skill(cfg)]
