"""Versioned, service-authored results for the six lighting query scenes.

Only the authorized MCP query tool supplies these facts. The model selects
queries, never supplies a result to a render tool. Missing evidence stays null.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

Scene = Literal["night", "lamp_alarms", "rtu", "rtu_alarms", "energy", "reconcile"]
Intent = Literal[
    "inspect_lamp",
    "compare_pole",
    "compare_circuit",
    "inspect_rtu",
    "inspect_rtu_alarm",
    "downstream",
    "energy_view",
    "decompose_energy",
    "reconcile_energy",
    "retry",
]
Scalar = StrictStr | StrictInt | StrictFloat | StrictBool | None
QUERY_TOOL = "query_lighting"
ACTION_NAME = "run:lighting.query"
TITLES = {
    "night": "整夜单灯运行",
    "lamp_alarms": "单灯报警追查",
    "rtu": "RTU 运行",
    "rtu_alarms": "RTU 报警",
    "energy": "能耗分析",
    "reconcile": "单灯 / RTU 能耗对账",
}
LAMP_REPORT = [
    "一、总体结论",
    "二、报警总览",
    "三、报警类型分布",
    "四、报警时间分布（按小时）",
    "五、重点道路分布",
    "六、重点异常单灯",
    "七、07:00 时点单灯运行状态",
    "八、能耗情况分析",
    "九、建议处置顺序",
]
RTU_REPORT = [
    "一、总体结论",
    "二、报警总览",
    "三、报警类型分布",
    "四、报警时间分布（按小时）",
    "五、重点RTU",
    "六、07:00 时点运行状态说明",
    "七、建议处置顺序",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Window(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("window end must follow start")
        return self


class Query(Contract):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    scope: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Shanghai"
    window: Window
    cutoff: AwareDatetime
    generated_at: AwareDatetime
    basis: Literal["night", "daily", "historical"]
    report_type: Literal["D"] | None = None
    # A 06:00 single-lamp cutoff must not silently shorten RTU night energy.
    rtu_energy_window: Window | None = None
    source: str = Field(min_length=1, max_length=200)
    coverage: str = Field(min_length=1, max_length=1000)
    filters: list[str] = Field(default_factory=list, max_length=30)
    missing: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def time_basis(self):
        try:
            zone = ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("unknown query timezone") from exc
        if self.basis == "daily":
            if self.report_type != "D":
                raise ValueError("daily queries require D reports")
            for stamp in (self.window.start, self.window.end):
                local = stamp.astimezone(zone)
                if any((local.hour, local.minute, local.second, local.microsecond)):
                    raise ValueError("daily boundaries must be local midnight")
        return self


class Metric(Contract):
    label: str = Field(max_length=100)
    value: Scalar = None
    unit: str = Field(default="", max_length=30)
    note: str = Field(default="", max_length=300)


class Evidence(Contract):
    label: str = Field(max_length=100)
    value: Scalar = None
    unit: str = Field(default="", max_length=30)
    at: AwareDatetime | None = None
    source: str = Field(max_length=200)
    note: str = Field(default="", max_length=600)


class Column(Contract):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="", max_length=30)
    type: Literal["text", "number", "time"] = "text"


class Action(Contract):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=100)
    intent: Intent
    row_id: str | None = Field(default=None, max_length=100)
    energy_view: Literal["night", "week", "volatility", "saving"] | None = None


class Row(Contract):
    id: str = Field(min_length=1, max_length=100)
    lamp_id: str | None = Field(default=None, max_length=100)
    rtu_id: str | None = Field(default=None, max_length=100)
    circuit_id: str | None = Field(default=None, max_length=100)
    pole_id: str | None = Field(default=None, max_length=100)
    alarm_id: str | None = Field(default=None, max_length=100)
    phase: str | None = Field(default=None, max_length=60)
    anchor: AwareDatetime | None = None
    evidence_window: Window | None = None
    # Historical membership must be established by the query service, not the UI.
    relationship_verified: bool = False
    values: dict[str, Scalar] = Field(default_factory=dict, max_length=50)
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    missing: list[str] = Field(default_factory=list, max_length=30)


class ReportSection(Contract):
    title: str = Field(max_length=100)
    content: str = Field(max_length=20000)


class Chart(Contract):
    title: str = Field(max_length=120)
    x_key: str = Field(max_length=60)
    x_label: str = Field(max_length=100)
    y: list[Column] = Field(max_length=8)
    rows: list[dict[str, Scalar]] = Field(max_length=1000)
    # Select a point to filter the already-returned list by this column.
    filter_key: str | None = Field(default=None, max_length=60)


class LightingResult(Contract):
    schema_version: Literal["lighting-query/v1"]
    scene: Scene
    status: Literal["success", "partial", "empty", "error"]
    query: Query
    summary: str = Field(max_length=2000)
    error: str | None = Field(default=None, max_length=1000)
    energy_view: Literal["night", "week", "volatility", "saving"] | None = None
    metrics: list[Metric] = Field(default_factory=list, max_length=12)
    columns: list[Column] = Field(min_length=1, max_length=24)
    rows: list[Row] = Field(default_factory=list, max_length=1000)
    row_count: int = Field(ge=0)
    complete: bool = False
    chart: Chart | None = None
    actions: list[Action] = Field(default_factory=list, max_length=4000)
    report: list[ReportSection] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def consistent(self):
        if self.row_count < len(self.rows) or (self.complete and self.row_count != len(self.rows)):
            raise ValueError("row coverage is inconsistent")
        ids = [row.id for row in self.rows]
        keys = [col.key for col in self.columns]
        action_ids = [action.id for action in self.actions]
        if len(set(ids)) != len(ids) or len(set(keys)) != len(keys) or len(set(action_ids)) != len(action_ids):
            raise ValueError("row, column and action ids must be unique")
        if any(action.row_id is not None and action.row_id not in ids for action in self.actions):
            raise ValueError("action refers to a missing row")
        if self.status == "error" and not self.error:
            raise ValueError("query errors need an explanation")
        if self.status == "empty" and (self.row_count or not self.complete):
            raise ValueError("only a complete zero-row query is empty")
        if self.scene == "reconcile" and self.query.basis != "daily":
            raise ValueError("reconciliation requires D daily reports")
        if self.scene == "energy":
            if self.energy_view is None:
                raise ValueError("energy requires an explicit view")
            if (self.energy_view == "night") != (self.query.basis == "night"):
                raise ValueError("night energy and daily views cannot mix time bases")
        if self.report:
            expected = (
                RTU_REPORT if self.scene == "rtu" else LAMP_REPORT if self.scene in {"night", "lamp_alarms"} else None
            )
            if expected and [section.title for section in self.report] != expected:
                raise ValueError("operation report must preserve the fixed template chapters")
        return self


def number(value: Scalar, upper: float = math.inf) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and 0 <= value < upper else None


def _stamp(value: Scalar) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.utcoffset() is not None else None
    except ValueError:
        return None


def normalize(result: LightingResult) -> LightingResult:
    """Apply known arithmetic and evidence boundaries, without inventing facts.

    Supplied aggregate metrics are the service's responsibility. Derived totals
    below are produced only for a complete returned population.
    """
    result = result.model_copy(deep=True)
    if result.status == "error":
        result.rows, result.metrics, result.report = [], [], []
        result.chart = None
        result.row_count, result.complete = 0, False
        result.summary = "查询失败,不能据此判断正常或零报警。"
        result.actions = [action for action in result.actions if action.intent == "retry" and action.row_id is None]
        return result
    if not result.rows and result.complete and result.status == "success":
        result.status = "empty"
    if not result.complete:
        result.query.missing.append("当前返回范围不完整;清单与图表不代表全网汇总。")
    theory_total = actual_total = 0.0
    saving_pairs = 0
    for row in result.rows:
        values = row.values
        if row.alarm_id:
            triggered, restored = _stamp(values.get("triggered_at")), _stamp(values.get("restored_at"))
            history = values.get("history_complete") is True
            status = "证据不足"
            if (
                history
                and triggered
                and triggered <= result.query.cutoff
                and (restored is None or restored >= triggered)
            ):
                if restored and restored <= result.query.cutoff:
                    status = "截止时点已解除"
                elif values.get("restored_at") is None or restored:
                    status = "截止时点未解除"
            values["status_at_cutoff"] = status
            if row.anchor is None:
                row.anchor = triggered
            if row.evidence_window is None and row.anchor:
                row.evidence_window = Window(
                    start=row.anchor - timedelta(minutes=10), end=row.anchor + timedelta(minutes=10)
                )
        if result.scene == "reconcile":
            lamp, rtu = number(values.get("lamp_kwh")), number(values.get("rtu_kwh"), 1500)
            # lamp_kwh is the aggregate AFTER each raw lamp's [0,100) filter.
            valid = (
                row.relationship_verified
                and values.get("lamp_filter_applied") is True
                and lamp is not None
                and rtu is not None
            )
            values["difference_kwh"] = round(lamp - rtu, 6) if valid else None
            values["ratio"] = round(lamp / rtu, 6) if valid and rtu > 0 else None
            values["status"] = ("倒挂" if lamp > rtu else "可比较") if valid else "证据不足"
            if not valid:
                row.missing.append("需有效 D 日报、单灯逐条有效值过滤及历史主挂载链路证据。")
        if result.scene == "energy" and result.energy_view == "saving":
            theory, actual = number(values.get("theoretical_kwh")), number(values.get("actual_kwh"))
            valid = theory is not None and theory > 0 and actual is not None
            rate = (theory - actual) / theory if valid else None
            values["calculated_rate"] = rate
            target = number(values.get("target_rate"))
            if target is not None and target > 1:
                target = None
            values["target_status"] = (
                ("达标" if rate >= target else "未达标")
                if rate is not None and target is not None
                else "未取得目标或有效能耗"
            )
            recorded = number(values.get("recorded_rate"))
            values["rate_consistency"] = (
                "指标一致性异常" if recorded == 0 and rate is not None and abs(rate) > 0.000001 else "待核对"
            )
            if valid:
                theory_total += theory
                actual_total += actual
                saving_pairs += 1
        if result.scene == "energy" and result.energy_view == "volatility":
            before, after = number(values.get("previous_kwh"), 1500), number(values.get("actual_kwh"), 1500)
            delta = after - before if before is not None and after is not None else None
            rate = delta / before if delta is not None and before > 0 else None
            values.update(
                change_kwh=delta,
                change_rate=rate,
                increase_flag=delta is not None and rate is not None and delta >= 50 and rate >= 0.3,
            )
        if result.scene == "energy" and result.energy_view == "night":
            before, after = number(values.get("previous_kwh")), number(values.get("actual_kwh"))
            old_minutes, minutes = number(values.get("previous_minutes")), number(values.get("minutes"))
            valid = (
                values.get("matched") is True
                and before is not None
                and after is not None
                and old_minutes is not None
                and old_minutes > 0
                and minutes is not None
            )
            duration = before / old_minutes * (minutes - old_minutes) if valid else None
            values["duration_kwh"] = duration
            values["other_kwh"] = after - before - duration if valid else None
            values["long_low_clue"] = minutes is not None and after is not None and minutes > 500 and after < 0.1
        if result.scene == "rtu_alarms":
            # These are evidence requirements, never protection/safety verdicts.
            kind = values.get("alarm_type")
            required = {
                "漏电": ["leakage_unit", "trip_record", "lockout", "post_trip_samples"],
                "缺相": ["day_night", "phase_mapping", "phase_current", "circuit_current", "related_break_alarm"],
                "过流": ["previous_two_days", "curve_rule", "rated_current", "actual_current"],
                "断路": ["lamp_kind", "continuous_current", "pre_alarm_current", "total_current"],
            }.get(kind, [])
            row.missing.extend(f"缺少专项证据: {key}" for key in required if values.get(key) is None)
            if kind == "过流":
                rated, actual = number(values.get("rated_current")), number(values.get("actual_current"))
                values["above_rated_rate"] = (
                    (actual - rated) / rated if rated is not None and rated > 0 and actual is not None else None
                )
    if result.scene == "energy" and result.energy_view == "saving" and result.complete:
        result.metrics.append(
            Metric(
                label="有效样本加权节能率",
                value=(theory_total - actual_total) / theory_total if theory_total > 0 else None,
                unit="ratio",
                note=f"有效配对 {saving_pairs}/{len(result.rows)},先合计理论与实际能耗",
            )
        )
    if result.query.missing or any(row.missing for row in result.rows):
        if result.status == "success":
            result.status = "partial"
    return result
