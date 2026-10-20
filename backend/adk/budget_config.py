from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BudgetConfig(BaseModel):
    """Per-skill budget gate config. Opt-in via ``tool_configs.budget``."""

    identity_key: str = Field(
        ...,
        description=(
            "Which ``User`` field the budget enforcer keys on. "
            "Examples: ``uid`` for user quotas, ``group_id`` for "
            "cohorts/classrooms, ``uid`` for per-user budgets, or ``domain`` "
            "for legacy org-level budgets. Required — there's no sensible default."
        ),
    )
    cost_multiplier: float = Field(
        default=1.0,
        gt=0.0,
        description=(
            "Scale the projected cost before the enforcer is consulted. "
            "Use >1.0 for expensive skills (e.g. code-grader = 3x). "
            "0.0 is rejected: zero-cost is what ``exempt: true`` is for. "
            "Negative values are rejected."
        ),
    )
    exempt: bool = Field(
        default=False,
        description=(
            "Bypass the gate entirely. The enforcer is not consulted "
            "and no log line is emitted. Use for system tools that "
            "must never be budget-gated (e.g. auth checks)."
        ),
    )
    missing_identity_policy: Literal["skip", "block"] = Field(
        default="skip",
        description=(
            "How to handle a missing/blank identity field. ``skip`` preserves "
            "the historical fail-open behaviour. ``block`` fails closed before "
            "the model call and is recommended for ``identity_key: uid`` "
            "in multi-user deployments."
        ),
    )

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _identity_key_not_empty(self) -> BudgetConfig:
        if not self.identity_key.strip():
            raise ValueError("identity_key must be a non-empty string")
        return self

    @classmethod
    def from_tool_configs(cls, tool_configs: dict[str, Any] | None) -> BudgetConfig | None:
        """Build the typed config from a raw ``tool_configs`` dict.

        - ``None`` / empty / missing ``budget`` key → ``None`` (skill exempt by absence)
        - ``budget`` present and a dict → validate (raises ValidationError on bad shape)
        - ``budget`` present but not a dict → ``None`` (tolerant: opt-in path,
          misconfiguration falls back to safe behaviour)
        """
        if not tool_configs:
            return None
        raw = tool_configs.get("budget")
        if raw is None or not isinstance(raw, dict):
            return None
        return cls.model_validate(raw)
