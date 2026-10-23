"""Public plan reports, real ADK schema/callback path and session isolation."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.adk.sessions.state import State
from google.adk.tools import FunctionTool

from adk import a2ui_task_plan_render  # noqa: F401 — production mapping registration
from adk.a2ui_result_render import render_for_emit
from adk.callbacks import _stash_surface_for_resume, make_a2ui_result_emitter
from agents.root_runtime import compose_root_skill, root_agent_skill
from db.models.root_agent import RootAgentConfig
from observability.timing import LatencyTracker, reset_current_tracker, set_current_tracker
from tests.support.state_doubles import ScopedState
from tools.task_plan import PLAN_INSTRUCTIONS, PLAN_STATE_PREFIX, update_task_plan


def _steps(status="pending", detail=""):
    return [{"id": "read", "title": "读取资料", "status": status, "detail": detail}]


def _context(state=None):
    return SimpleNamespace(state=state if state is not None else {}, invocation_id="plan-run")


@pytest.mark.asyncio
async def test_real_function_tool_declaration_and_json_args():
    tool = FunctionTool(update_task_plan)
    schema = tool._get_declaration().parameters_json_schema
    # Some providers use parameters instead; validate the ADK-generated schema.
    declaration = tool._get_declaration().model_dump(exclude_none=True)
    assert "tool_context" not in json.dumps(declaration)
    assert "steps" in json.dumps(schema or declaration)
    result = await tool.run_async(args={"title": "检查资料", "steps": _steps()}, tool_context=_context(State({}, {})))
    assert result["task_plan"]["revision"] == 1


def test_update_conflict_repeat_and_stable_identity():
    ctx = _context()
    first = update_task_plan("检查资料", _steps(), tool_context=ctx)["task_plan"]
    args = {"plan_id": first["plan_id"], "tool_context": ctx}
    conflict = update_task_plan("检查资料", _steps("running"), **args)
    assert conflict == {"error": "revision_conflict", "current_revision": 1, "current_plan": first}
    second = update_task_plan("检查资料", _steps("running"), expected_revision=1, **args)["task_plan"]
    assert second["plan_id"] == first["plan_id"] and second["revision"] == 2
    assert update_task_plan("检查资料", _steps("running"), expected_revision=1, **args)["task_plan"] == second
    assert len(ctx.state) == 1


@pytest.mark.parametrize(
    "steps",
    [
        [],
        _steps() * 2,
        _steps() * 21,
        _steps("invented"),
        _steps("failed"),
        _steps("needs_input"),
        [{"id": "a/b", "title": "bad"}],
        [{"id": "x", "title": " "}],
    ],
)
def test_invalid_plan_does_not_mutate_state(steps):
    ctx = _context()
    assert update_task_plan("检查资料", steps, tool_context=ctx)["error"] == "invalid_plan"
    assert not ctx.state


def test_session_scope_and_untrusted_plan_ids():
    app, user = {}, {}
    a = _context(ScopedState(app_store=app, user_store=user))
    b = _context(ScopedState(app_store=app, user_store=user))
    plan = update_task_plan("检查资料", _steps(), tool_context=a)["task_plan"]
    assert update_task_plan("检查资料", _steps(), plan_id=plan["plan_id"], tool_context=b)["error"] == "plan_not_found"
    assert update_task_plan("检查资料", _steps(), plan_id="app:private", tool_context=a)["error"] == "invalid_plan_id"
    assert not app and not user
    assert update_task_plan("检查资料", _steps())["error"] == "session_required"


def test_session_plan_limit_does_not_prevent_updating():
    ctx = _context()
    for _ in range(25):
        plan = update_task_plan("检查资料", _steps(), tool_context=ctx)["task_plan"]
    assert update_task_plan("新的计划", _steps(), tool_context=ctx)["error"] == "session_plan_limit"
    assert "task_plan" in update_task_plan(
        "检查资料", _steps("completed"), plan_id=plan["plan_id"], expected_revision=1, tool_context=ctx
    )


def test_registered_render_is_valid_v09_and_declines_errors():
    from a2ui.basic_catalog import BasicCatalog
    from a2ui.schema.manager import A2uiSchemaManager
    from a2ui.schema.validator import A2uiValidator

    result = update_task_plan("检查资料", _steps("needs_input", "请补充统计日期"), tool_context=_context())
    rendered = render_for_emit("update_task_plan", result)
    assert rendered.surface_id == f"task_plan:{result['task_plan']['plan_id']}"
    assert rendered.artifact["displayOnly"] and rendered.artifact["placement"] == "chat"
    catalog = A2uiSchemaManager(version="0.9", catalogs=[BasicCatalog.get_config("0.9")])._supported_catalogs[0]
    A2uiValidator(catalog).validate(rendered.messages)
    text = json.dumps(rendered.messages, ensure_ascii=False)
    assert "待补充" in text and "请补充统计日期" in text
    assert '"Button"' not in text
    assert render_for_emit("update_task_plan", {"error": "revision_conflict"}) is None


def test_callback_emits_real_custom_and_durably_preserves_original_position():
    ctx = _context(State({}, {}))
    tracker = LatencyTracker()
    token = set_current_tracker(tracker)
    try:
        emitter = make_a2ui_result_emitter()
        tool = FunctionTool(update_task_plan)
        first = update_task_plan("检查资料", _steps(), tool_context=ctx)
        emitter(tool=tool, args={}, tool_context=ctx, tool_response=first)
        surface = f"task_plan:{first['task_plan']['plan_id']}"
        key = f"a2ui_surface:{surface}"
        original = json.loads(ctx.state[key])
        second = update_task_plan(
            "检查资料",
            _steps("failed", "资料不可读"),
            plan_id=first["task_plan"]["plan_id"],
            expected_revision=1,
            tool_context=ctx,
        )
        emitter(tool=tool, args={}, tool_context=ctx, tool_response=second)
        updated = json.loads(ctx.state[key])
        assert original["createdAt"] == updated["createdAt"]
        assert "资料不可读" in json.dumps(updated, ensure_ascii=False)
        # This is the production event queue, not a render-only mock.
        events = [event.model_dump(by_alias=True) for event in tracker.drain_stage_events()]
        surfaces = [event for event in events if event.get("name") == "A2UI_SURFACE"]
        assert len(surfaces) == 2
        assert all(event["value"]["surfaceId"] == surface for event in surfaces)
        assert ctx.state[f"{PLAN_STATE_PREFIX}{first['task_plan']['plan_id']}"]["revision"] == 2
    finally:
        reset_current_tracker(token)


@pytest.mark.parametrize("raw", ["corrupt", '{"createdAt":true}', '{"createdAt":-1}', '{"createdAt":NaN}'])
def test_bad_prior_timestamp_does_not_block_current_render(raw):
    ctx = _context({"a2ui_surface:task_plan:test": raw})
    rendered = SimpleNamespace(surface_id="task_plan:test", messages=[{"test": True}], artifact={})
    _stash_surface_for_resume(ctx, rendered, "new-source", "update_task_plan")
    assert json.loads(ctx.state["a2ui_surface:task_plan:test"])["createdAt"] > 0


def test_root_binding_is_explicit_and_permission_is_rechecked():
    from adk.callbacks import make_permission_enforcer
    from auth.models import User
    from auth.permissions import ToolPermissionDenied

    root = RootAgentConfig(tools=["update_task_plan"])
    assert PLAN_INSTRUCTIONS in compose_root_skill(root_agent_skill(root), root).instructions
    empty = RootAgentConfig()
    assert PLAN_INSTRUCTIONS not in compose_root_skill(root_agent_skill(empty), empty).instructions
    gate = make_permission_enforcer(
        "u@example.com", "example.com", user=User(uid="u", email="u@example.com", domain="example.com"), root_agent=True
    )
    tool = FunctionTool(update_task_plan)
    ctx = _context()
    ctx.agent_name = "root-agent"
    with (
        patch("config.platform_config.get_platform_config", return_value=SimpleNamespace(agent=root)),
        patch("auth.capability_access.authorized_root_config", return_value=root),
    ):
        assert gate(tool, {}, ctx) is None
    with (
        patch("config.platform_config.get_platform_config", return_value=SimpleNamespace(agent=empty)),
        patch("auth.capability_access.authorized_root_config", return_value=empty),
    ):
        with pytest.raises(ToolPermissionDenied):
            gate(tool, {}, ctx)


def test_http_fixture_updates_the_saved_plan_and_stops_after_tool_return():
    from tests.fixtures.model_setup_probe import plan_reply

    ctx = _context(State({}, {}))
    create = [{"role": "user", "content": "TASK-PLAN-CREATE-1234abcd"}]
    call, finish = plan_reply(create)
    assert finish == "tool_calls"
    args = json.loads(call["tool_calls"][0]["function"]["arguments"])
    result = update_task_plan(**args, tool_context=ctx)
    messages = [*create, call, {"role": "tool", "content": json.dumps({"result": result})}]
    assert plan_reply(messages)[1] == "stop"
    messages.append({"role": "user", "content": "TASK-PLAN-UPDATE-1234abcd"})
    call, finish = plan_reply(messages)
    assert finish == "tool_calls"
    args = json.loads(call["tool_calls"][0]["function"]["arguments"])
    assert args["plan_id"] == result["task_plan"]["plan_id"]
    assert args["expected_revision"] == 1
    updated = update_task_plan(**args, tool_context=ctx)
    assert updated["task_plan"]["revision"] == 2
    assert updated["task_plan"]["steps"][1]["status"] == "needs_input"
    assert plan_reply([*messages, call, {"role": "tool", "content": json.dumps(updated)}])[1] == "stop"
    assert plan_reply([{"role": "user", "content": "MODEL-SETUP-ROOT-1234abcd"}]) is None
