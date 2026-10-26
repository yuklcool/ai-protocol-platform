"""Resolve opaque UI action ids against the server's saved result only."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from google.adk.sessions.base_session_service import GetSessionConfig

from adk.session import get_session_service
from auth.capability_access import mcp_call_allowed
from db.chat_sessions import app_name_for_session
from lighting.results import ACTION_NAME, QUERY_TOOL, LightingResult


def resolve_saved_action(saved: dict, context: dict | None, *, now: datetime | None = None) -> dict:
    if not isinstance(context, dict) or set(context) != {"actionId"}:
        raise HTTPException(422, "照明动作只接受 actionId,设备与时间从服务器结果解析。")
    if not isinstance(saved, dict) or saved.get("toolName") != QUERY_TOOL:
        raise HTTPException(409, "照明结果来源不可用,请重新查询。")
    messages = saved.get("messages") or []
    roots = [
        message["updateDataModel"]["value"]
        for message in messages
        if isinstance(message, dict)
        and isinstance(message.get("updateDataModel"), dict)
        and message["updateDataModel"].get("path") == "/"
    ]
    root = roots[-1] if roots else None
    if not isinstance(root, dict) or not root.get("server_id"):
        raise HTTPException(409, "照明数据源不可用,请重新查询。")
    try:
        result = LightingResult.model_validate(
            {key: value for key, value in root.items() if key not in {"kind", "title", "server_id"}}
        )
    except ValueError as exc:
        raise HTTPException(409, "保存的照明结果不完整,请重新查询。") from exc
    now = now or datetime.now(UTC)
    if result.query.generated_at > now + timedelta(minutes=5) or now - result.query.generated_at > timedelta(days=1):
        raise HTTPException(409, "历史交互已过期,请将参数放入草稿后重新查询。")
    action = next((item for item in result.actions if item.id == context["actionId"]), None)
    if action is None or (result.status == "error" and action.intent != "retry"):
        raise HTTPException(403, "此照明动作未获授权。")
    row = next((item for item in result.rows if item.id == action.row_id), None) if action.row_id else None
    needs_relation = (
        action.intent in {"compare_pole", "compare_circuit", "inspect_rtu", "downstream", "reconcile_energy"}
        and row is not None
    )
    if needs_relation and not row.relationship_verified:
        raise HTTPException(409, "历史设备归属证据不足,不能据此扩大查询。")
    required = {
        "inspect_lamp": "lamp_id",
        "compare_pole": "pole_id",
        "compare_circuit": "circuit_id",
        "inspect_rtu": "rtu_id",
        "inspect_rtu_alarm": "alarm_id",
        "downstream": "rtu_id",
    }.get(action.intent)
    if required and (row is None or getattr(row, required) is None):
        raise HTTPException(409, "追查缺少必要设备或报警标识,请重新查询。")
    if action.intent in {"compare_circuit", "inspect_rtu_alarm"} and (row is None or not row.rtu_id):
        raise HTTPException(409, "回路与报警追查需要明确的 RTU 归属。")
    request = {
        "intent": action.intent,
        "source_query_id": result.query.id,
        "scene": result.scene,
        "scope": result.query.scope,
        "window": result.query.window.model_dump(mode="json"),
        "timezone": result.query.timezone,
        "cutoff": result.query.cutoff.isoformat(),
        "basis": result.query.basis,
        "report_type": result.query.report_type,
        "rtu_energy_window": result.query.rtu_energy_window.model_dump(mode="json")
        if result.query.rtu_energy_window
        else None,
        "energy_view": action.energy_view or result.energy_view,
    }
    if row:
        request["device"] = {
            key: getattr(row, key) for key in ("lamp_id", "rtu_id", "circuit_id", "pole_id", "alarm_id", "phase")
        }
        request["anchor"] = row.anchor.isoformat() if row.anchor else None
        request["evidence_window"] = row.evidence_window.model_dump(mode="json") if row.evidence_window else None
    return {"server_id": root["server_id"], "request": request}


async def validate_action(idx, user, surface_id: str, name: str, context: dict | None) -> dict | None:
    if not surface_id.startswith("lighting:") and not name.startswith("run:lighting."):
        return None
    if name != ACTION_NAME or idx.owner_uid != user.uid:
        raise HTTPException(403, "不能执行此会话的照明查询动作。")
    session = await get_session_service().get_session(
        app_name=app_name_for_session(idx),
        user_id=user.uid,
        session_id=idx.session_id,
        config=GetSessionConfig(num_recent_events=1),
    )
    raw = (getattr(session, "state", {}) or {}).get(f"a2ui_surface:{surface_id}")
    try:
        saved = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError as exc:
        raise HTTPException(409, "保存的照明结果不可用。") from exc
    canonical = resolve_saved_action(saved, context)
    if not mcp_call_allowed(user, canonical["server_id"], QUERY_TOOL):
        raise HTTPException(403, "照明 MCP 已停用或查询权限已撤销。")
    return canonical
