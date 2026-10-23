"""Search projection of explicitly reported plans; never infer success from a Run."""

from collections.abc import Mapping

TASK_STATUSES = {"pending", "running", "completed", "failed", "cancelled", "needs_input", "unplanned"}


def task_projection(state: Mapping) -> dict:
    from tools.task_plan import PLAN_STATE_PREFIX, TaskPlan

    plans = []
    for key, raw in state.items():
        if not str(key).startswith(PLAN_STATE_PREFIX):
            continue
        try:
            plans.append(TaskPlan.model_validate(raw))
        except ValueError:
            continue
    if not plans:
        return {"taskStatus": "unplanned", "taskTitle": None, "taskProgress": None}
    plan = max(plans, key=lambda item: item.reported_at)
    statuses = [step.status for step in plan.steps]
    if all(status == "completed" for status in statuses):
        status = "completed"
    elif "failed" in statuses:
        status = "failed"
    elif "needs_input" in statuses:
        status = "needs_input"
    elif "running" in statuses:
        status = "running"
    elif "cancelled" in statuses:
        status = "cancelled"
    else:
        status = "pending"
    return {
        "taskStatus": status,
        "taskTitle": plan.title,
        "taskProgress": {"completed": statuses.count("completed"), "total": len(statuses)},
    }
