"""Business boundaries and the registered A2UI mapping; run in GitHub CI."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from adk.a2ui_lighting_render import lighting_to_a2ui, unwrap
from lighting.actions import resolve_saved_action, validate_action
from lighting.results import LightingResult, normalize
from tests.fixtures.lighting_results import fixture


def root(result):
    return lighting_to_a2ui(result, SimpleNamespace(state={"temp:_lighting_mcp_server": "lighting-mcp"}))[-1][
        "updateDataModel"
    ]["value"]


def saved(result):
    return {
        "toolName": "query_lighting",
        "messages": lighting_to_a2ui(result, SimpleNamespace(state={"temp:_lighting_mcp_server": "lighting-mcp"})),
    }


@pytest.mark.parametrize("scene", ["night", "lamp_alarms", "rtu", "rtu_alarms", "energy", "reconcile"])
def test_six_scenes_have_provenance_basic_fallback_and_host_model(scene):
    from a2ui.basic_catalog import BasicCatalog
    from a2ui.schema.manager import A2uiSchemaManager
    from a2ui.schema.validator import A2uiValidator

    result = root(fixture(scene))
    assert result["kind"] == "lighting"
    assert result["query"]["timezone"] == "Asia/Shanghai"
    assert result["server_id"] == "lighting-mcp"
    assert result["rows"]
    assert "schema_version" in result
    messages = lighting_to_a2ui(fixture(scene))
    assert all(message["version"] == "v0.9" for message in messages)
    assert messages[0]["createSurface"]["catalogId"].endswith("v0_9/basic_catalog.json")
    catalog = A2uiSchemaManager(version="0.9", catalogs=[BasicCatalog.get_config("0.9")])._supported_catalogs[0]
    A2uiValidator(catalog).validate(messages)


@pytest.mark.parametrize(
    "wrap",
    [
        lambda value: {"result": json.dumps({"result": value})},
        lambda value: {"structuredContent": value, "content": []},
        lambda value: {"content": [{"type": "text", "text": json.dumps(value)}]},
    ],
)
def test_mcp_wrapping(wrap):
    result = fixture()
    assert unwrap(wrap(result)) == result


@pytest.mark.parametrize(
    "value", [{"isError": True, "structuredContent": fixture()}, {"content": []}, {"error": "offline"}, "not json"]
)
def test_errors_and_invalid_envelopes_never_become_zero_alarm_or_normal(value):
    result = root(value)
    assert result["status"] == "error"
    assert "metrics" not in result
    assert result["actions"] == []


def test_historical_restore_after_cutoff_does_not_rewrite_the_past():
    result = fixture("lamp_alarms")
    cutoff = datetime.fromisoformat(result["query"]["cutoff"])
    result["rows"][0]["values"]["restored_at"] = (cutoff + timedelta(hours=1)).isoformat()
    assert root(result)["rows"][0]["values"]["status_at_cutoff"] == "截止时点未解除"
    result["rows"][0]["values"]["history_complete"] = False
    assert root(result)["rows"][0]["values"]["status_at_cutoff"] == "证据不足"


def test_evidence_defaults_to_plus_minus_ten_minutes_and_preserves_context():
    result = fixture()
    request = resolve_saved_action(saved(result), {"actionId": "circuit-row-1"})["request"]
    assert request["device"]["alarm_id"] == "alarm-001"
    assert request["device"]["rtu_id"] == "RTU-017"
    assert request["device"]["circuit_id"] == "2"
    assert datetime.fromisoformat(request["evidence_window"]["end"]) - datetime.fromisoformat(
        request["evidence_window"]["start"]
    ) == timedelta(minutes=20)
    assert request["window"] == result["query"]["window"]


def test_six_oclock_lamp_cutoff_preserves_separate_rtu_seven_oclock_window():
    result = fixture()
    result["query"]["rtu_energy_window"] = dict(result["query"]["window"])
    end = datetime.fromisoformat(result["query"]["window"]["end"])
    result["query"]["window"]["end"] = (end - timedelta(hours=1)).isoformat()
    request = resolve_saved_action(saved(result), {"actionId": "rtu-row-1"})["request"]
    assert request["window"]["end"] != request["rtu_energy_window"]["end"]


def test_weighted_saving_uses_sums_and_missing_target_does_not_pass():
    result = root(fixture("energy", "saving"))
    assert result["metrics"][-1]["value"] == pytest.approx(0.14)  # not (50% + 10%) / 2
    assert result["rows"][0]["values"]["target_status"] == "未取得目标或有效能耗"


def test_incomplete_list_does_not_generate_whole_scope_weighted_metric():
    result = fixture("energy", "saving")
    result.update(complete=False, row_count=9000)
    rendered = root(result)
    assert rendered["status"] == "partial"
    assert all(metric["label"] != "有效样本加权节能率" for metric in rendered["metrics"])


@pytest.mark.parametrize(
    "before,after,flag",
    [
        (100, 149, False),
        (200, 250, False),
        (100, 150, True),
        (0, 100, False),
        (None, 100, False),
        (200, 50, False),
        (1450, 1500, False),
    ],
)
def test_rtu_increase_requires_both_thresholds_and_valid_previous(before, after, flag):
    result = fixture("energy", "volatility")
    result["rows"][0]["values"].update(previous_kwh=before, actual_kwh=after)
    assert root(result)["rows"][0]["values"]["increase_flag"] is flag


def test_duration_split_does_not_explain_unmatched_or_zero_baseline():
    result = fixture("energy", "night")
    assert root(result)["rows"][0]["values"]["duration_kwh"] == pytest.approx(1)
    assert root(result)["rows"][1]["values"]["duration_kwh"] is None
    result["rows"][0]["values"]["previous_minutes"] = 0
    assert root(result)["rows"][0]["values"]["duration_kwh"] is None


@pytest.mark.parametrize(
    "rtu,verified,expected_difference",
    [(0, True, 20), (None, True, None), (1500, True, None), (-1, True, None), (10, False, None)],
)
def test_reconcile_zero_denominator_missing_filters_and_membership(rtu, verified, expected_difference):
    result = fixture("reconcile")
    result["rows"][0]["values"]["rtu_kwh"] = rtu
    result["rows"][0]["relationship_verified"] = verified
    row = root(result)["rows"][0]
    assert row["values"]["difference_kwh"] == expected_difference
    if rtu in (0, None) or not verified:
        assert row["values"]["ratio"] is None


def test_day_report_and_fixed_report_template_are_validated():
    result = fixture("reconcile")
    result["query"]["basis"] = "night"
    with pytest.raises(ValidationError):
        LightingResult.model_validate(result)
    result = fixture()
    result["report"].pop()
    with pytest.raises(ValidationError):
        LightingResult.model_validate(result)


def test_specialized_alarm_evidence_is_not_inferred_from_one_reading():
    result = root(fixture("rtu_alarms"))
    assert any("trip_record" in gap for gap in result["rows"][0]["missing"])
    assert result["rows"][1]["values"]["above_rated_rate"] is None


@pytest.mark.parametrize(
    "context,status",
    [
        ({"actionId": "missing"}, 403),
        ({"actionId": "circuit-row-1", "rtu_id": "forged"}, 422),
        ({"actionId": "circuit-row-2"}, 409),
    ],
)
def test_opaque_actions_reject_forgery_and_unverified_relations(context, status):
    with pytest.raises(HTTPException) as error:
        resolve_saved_action(saved(fixture()), context)
    assert error.value.status_code == status


def test_expired_actions_require_a_new_query():
    result = fixture()
    with pytest.raises(HTTPException) as error:
        resolve_saved_action(saved(result), {"actionId": "retry"}, now=datetime.now(UTC) + timedelta(days=2))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_cross_user_rejected_before_loading_saved_data(monkeypatch):
    service = SimpleNamespace(get_session=AsyncMock())
    monkeypatch.setattr("lighting.actions.get_session_service", lambda: service)
    with pytest.raises(HTTPException) as error:
        await validate_action(
            SimpleNamespace(owner_uid="owner"),
            SimpleNamespace(uid="other"),
            "lighting:id",
            "run:lighting.query",
            {"actionId": "retry"},
        )
    assert error.value.status_code == 403
    service.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_revoked_mcp_denies_action_even_with_a_valid_saved_result(monkeypatch):
    result = fixture()
    service = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(state={"a2ui_surface:lighting:id": json.dumps(saved(result))})
        )
    )
    monkeypatch.setattr("lighting.actions.get_session_service", lambda: service)
    monkeypatch.setattr("lighting.actions.app_name_for_session", lambda _idx: "app")
    monkeypatch.setattr("lighting.actions.mcp_call_allowed", lambda *_args: False)
    with pytest.raises(HTTPException) as error:
        await validate_action(
            SimpleNamespace(owner_uid="owner", session_id="s1"),
            SimpleNamespace(uid="owner"),
            "lighting:id",
            "run:lighting.query",
            {"actionId": "retry"},
        )
    assert error.value.status_code == 403


def test_error_result_strips_stale_metrics_rows_and_reports():
    result = normalize(LightingResult.model_validate(fixture(status="error")))
    assert result.rows == result.metrics == result.report == []
    assert result.chart is None
    assert result.row_count == 0


def test_main_callback_emits_and_stashes_only_a_tagged_mcp_result(monkeypatch):
    from unittest.mock import MagicMock

    from adk.callbacks import make_a2ui_result_emitter

    tracker = MagicMock()
    monkeypatch.setattr("observability.timing.get_current_tracker", lambda: tracker)
    payload = fixture(query_id="callback-result")
    context = SimpleNamespace(state={}, invocation_id="fixture")
    tool = SimpleNamespace(name="query_lighting", _aitana_mcp_server_id="lighting-mcp")
    make_a2ui_result_emitter()(tool=tool, args={}, tool_context=context, tool_response={"structuredContent": payload})
    tracker.emit_a2ui_surface.assert_called_once()
    assert "a2ui_surface:lighting:callback-result" in context.state
    assert not any(key.startswith("app:") for key in context.state)
    other = SimpleNamespace(state={}, invocation_id="untrusted")
    make_a2ui_result_emitter()(
        tool=SimpleNamespace(name="query_lighting"), args={}, tool_context=other, tool_response=payload
    )
    assert not other.state


def test_tool_boundary_overrides_forged_model_arguments_and_rejects_other_tools(monkeypatch):
    from unittest.mock import MagicMock

    from adk.callbacks import make_permission_enforcer
    from auth.permissions import ToolPermissionDenied

    monkeypatch.setattr("auth.capability_access.mcp_call_allowed", lambda *_args: True)
    monkeypatch.setattr("observability.timing.get_current_tracker", lambda: MagicMock())
    canonical = {"server_id": "lighting-mcp", "request": {"intent": "compare_circuit", "device": {"rtu_id": "RTU-017"}}}
    context = SimpleNamespace(
        state={"a2ui_action_trigger": {"name": "run:lighting.query"}, "lighting_query_action": canonical}
    )
    enforcer = make_permission_enforcer(
        "owner@example.com", "example.com", user=SimpleNamespace(uid="owner"), root_agent=True
    )
    args = {"request": {"device": {"rtu_id": "FORGED"}}, "extra": "untrusted"}
    enforcer(SimpleNamespace(name="query_lighting", _aitana_mcp_server_id="lighting-mcp"), args, context)
    assert args == {"request": canonical["request"]}
    with pytest.raises(ToolPermissionDenied):
        enforcer(SimpleNamespace(name="control_device", _aitana_mcp_server_id="lighting-mcp"), {}, context)
    with pytest.raises(ToolPermissionDenied):
        enforcer(SimpleNamespace(name="query_lighting", _aitana_mcp_server_id="different-source"), {}, context)
