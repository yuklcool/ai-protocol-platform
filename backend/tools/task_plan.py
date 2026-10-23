"""Session-scoped public plan reporting, without executing any business action."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from google.adk.tools import ToolContext
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PLAN_STATE_PREFIX = "task_plan:"
PLAN_INSTRUCTIONS = """For tasks with several meaningful business steps, use update_task_plan before
executing them, then update the same plan_id and expected_revision as work progresses.
Report only short public steps, never private reasoning. Preserve step ids across updates.
Mark completed only after the actual work succeeds; report failed or needs_input with a
clear detail when appropriate. A tool return or RUN_FINISHED alone never proves business
completion. Do not create a plan for a simple answer. This tool only reports progress:
it does not execute, approve, retry or resume work. Ask for confirmation through the
existing request_confirmation tool when required, never through a fabricated plan button."""


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    status: Literal["pending", "running", "completed", "failed", "cancelled", "needs_input"] = "pending"
    detail: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def explain_blocker(self):
        if self.status in {"failed", "needs_input"} and not self.detail:
            raise ValueError("failed/needs_input steps require a public detail")
        return self


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    steps: list[PlanStep] = Field(min_length=1, max_length=20)
    reported_at: str

    @model_validator(mode="after")
    def unique_steps(self):
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        return self


def update_task_plan(
    title: str,
    steps: list[PlanStep],
    plan_id: str = "",
    expected_revision: int = 0,
    tool_context: ToolContext = None,
) -> dict:
    """Report a short public business plan and its current step statuses in chat.

    This only records progress; it does not execute, approve or resume tasks.
    Never include hidden reasoning, credentials or unsupported success claims.

    Args:
        title: Short public task title.
        steps: Complete ordered steps, each with a stable id, title, status
            (pending/running/completed/failed/cancelled/needs_input), and optional
            public detail. failed/needs_input require detail explaining the blocker.
        plan_id: Omit for a NEW task. For updates copy the returned plan_id exactly.
        expected_revision: Omit for creation. For updates copy the last returned
            revision. On revision_conflict reconcile with current_plan before updating.
    """
    if tool_context is None or getattr(tool_context, "state", None) is None:
        return {"error": "session_required"}
    state = tool_context.state
    current = None
    if not isinstance(plan_id, str):
        return {"error": "invalid_plan_id"}
    if plan_id:
        # No user/app scope, arbitrary state path or cross-session plan lookup.
        if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
            return {"error": "invalid_plan_id"}
        raw = state.get(f"{PLAN_STATE_PREFIX}{plan_id}")
        if raw is None:
            return {"error": "plan_not_found"}
        try:
            current = TaskPlan.model_validate(raw)
        except ValidationError:
            return {"error": "invalid_saved_plan"}
    else:
        if expected_revision != 0:
            return {"error": "new_plan_requires_revision_zero"}
        view = state.to_dict() if hasattr(state, "to_dict") else state
        if sum(str(key).startswith(PLAN_STATE_PREFIX) for key in view) >= 25:
            return {"error": "session_plan_limit", "message": "请继续更新已有计划,或为新任务创建新会话。"}

    try:
        candidate = TaskPlan(
            plan_id=plan_id or uuid4().hex,
            revision=current.revision + 1 if current else 1,
            title=title,
            steps=steps,
            reported_at=datetime.now(UTC).isoformat(),
        )
    except ValidationError:
        return {"error": "invalid_plan", "message": "请检查标题、步骤编号、状态及失败/待补充原因。最多20步。"}

    if current:
        if candidate.title == current.title and candidate.steps == current.steps:
            return {"task_plan": current.model_dump()}
        if expected_revision != current.revision:
            return {
                "error": "revision_conflict",
                "current_revision": current.revision,
                "current_plan": current.model_dump(),
            }

    state[f"{PLAN_STATE_PREFIX}{candidate.plan_id}"] = candidate.model_dump()
    return {"task_plan": candidate.model_dump()}
