"""Explicit plan result → standard A2UI chat card, via the shared emitter."""

from typing import Any

from pydantic import ValidationError

from adk.a2ui_ppa_render import _Tree
from adk.a2ui_result_render import register
from tools.task_plan import TaskPlan

_STATUS = {
    "pending": "待执行",
    "running": "执行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "needs_input": "待补充",
}


def task_plan_to_a2ui(result: Any, tool_context: Any = None) -> list[dict] | None:
    if not isinstance(result, dict) or "error" in result:
        return None
    try:
        plan = TaskPlan.model_validate(result.get("task_plan"))
    except ValidationError:
        return None
    tree = _Tree()
    completed = sum(step.status == "completed" for step in plan.steps)
    children = [tree.text(f"任务计划 · 已完成 {completed}/{len(plan.steps)} 步", variant="h5")]
    for number, step in enumerate(plan.steps, 1):
        parts = [tree.text(f"{number}. {step.title} · {_STATUS[step.status]}")]
        if step.detail:
            parts.append(tree.text(step.detail))
        children.append(tree.card(tree.column(parts)))
    children.append(tree.text("状态为助手最近一次报告。继续任务可在对话中提出。"))
    tree.root(children)
    return tree.messages()


register(
    task_plan_to_a2ui,
    tool_names=["update_task_plan"],
    name="task_plan",
    surface=lambda result: f"task_plan:{result['task_plan']['plan_id']}",
    artifact_meta=lambda result: {
        "kind": "task-plan",
        "title": result["task_plan"]["title"],
        "placement": "chat",
        "displayOnly": True,
        "completedSummary": (
            f"已完成 · {len(result['task_plan']['steps'])} 个步骤 · 展开计划"
            if all(step["status"] == "completed" for step in result["task_plan"]["steps"])
            else None
        ),
    },
)
