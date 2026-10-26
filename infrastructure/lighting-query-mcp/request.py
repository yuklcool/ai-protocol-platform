"""Bounded business inputs; SQL and UI facts are never model parameters."""

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from lighting.results import Intent, Scene, Window


class Device(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lamp_id: str | None = Field(default=None, max_length=100)
    rtu_id: str | None = Field(default=None, max_length=100)
    circuit_id: str | None = Field(default=None, max_length=100)
    pole_id: str | None = Field(default=None, max_length=100)
    alarm_id: str | None = Field(default=None, max_length=100)
    phase: str | None = Field(default=None, max_length=60)


class LightingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: Scene
    energy_view: Literal["night", "week", "volatility", "saving"] | None = None
    scope: str = Field(default="全系统", min_length=1, max_length=200)
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    window: Window | None = None
    cutoff: AwareDatetime | None = None
    basis: Literal["night", "daily", "historical"] | None = None
    report_type: Literal["D"] | None = None
    rtu_energy_window: Window | None = None
    intent: Intent | None = None
    source_query_id: str | None = Field(default=None, max_length=80)
    device: Device = Field(default_factory=Device)
    anchor: AwareDatetime | None = None
    evidence_window: Window | None = None
    limit: int = Field(default=200, ge=1, le=500)

    @model_validator(mode="after")
    def bounded(self):
        if self.scene == "energy" and self.energy_view is None:
            self.energy_view = "night"
        if self.intent == "inspect_lamp":
            if not self.device.lamp_id:
                raise ValueError("单灯追查需要明确灯源")
            self.scene = "night"
        elif self.intent == "inspect_rtu_alarm":
            if not self.device.alarm_id or not self.device.rtu_id:
                raise ValueError("报警追查需要明确 RTU 和报警")
            self.scene = "rtu_alarms"
        elif self.intent == "inspect_rtu":
            if not self.device.rtu_id:
                raise ValueError("RTU 追查需要设备标识")
            self.scene = "rtu"
        elif self.intent in {"energy_view", "decompose_energy"}:
            self.scene = "energy"
        elif self.intent not in {None, "retry"}:
            raise ValueError("历史挂载关系尚未获得可信证据,此跨层级追查暂不可用")
        if any((self.device.circuit_id, self.device.pole_id, self.device.phase)):
            raise ValueError("回路、灯杆、相位范围需先核实历史映射,不能静默忽略")
        if self.scene == "energy" and self.device.lamp_id and self.energy_view != "night":
            raise ValueError("单灯范围不能切换到 RTU 日报或全系统节能率")
        return self

    def resolve(self, now: datetime) -> "LightingRequest":
        req = self.model_copy(deep=True)
        now = now.astimezone(ZoneInfo(req.timezone))
        daily = req.scene == "reconcile" or (req.scene == "energy" and req.energy_view != "night")
        expected_basis = "daily" if daily else "night"
        if req.evidence_window and req.intent in {"inspect_lamp", "inspect_rtu_alarm", "inspect_rtu"}:
            req.window = req.evidence_window
            req.basis = "historical"
            req.report_type = None
        elif req.basis is not None and req.basis != expected_basis:
            raise ValueError("时间基础与场景不一致")
        else:
            req.basis = expected_basis
        if req.window is None:
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if daily:
                days = 30 if req.energy_view == "volatility" else 7 if req.scene == "energy" else 1
                start = end - timedelta(days=days)
            else:
                end = end.replace(hour=7)
                if end > now:
                    end -= timedelta(days=1)
                start = (end - timedelta(days=1)).replace(hour=18)
            req.window = Window(start=start, end=end)
        if req.window.end > now or req.window.end - req.window.start > timedelta(days=31):
            raise ValueError("不能查询未来或超过 31 天的窗口")
        if not daily and req.window.end - req.window.start > timedelta(days=2):
            raise ValueError("夜间或历史证据查询最多 48 小时")
        if req.cutoff is None:
            req.cutoff = req.window.end
        if req.cutoff > now or req.cutoff < req.window.end:
            raise ValueError("截止时点不能早于窗口结束或晚于当前时间")
        if daily:
            req.report_type = "D"
        if req.rtu_energy_window:
            if daily or req.rtu_energy_window.end > now:
                raise ValueError("独立 RTU 夜间窗口不能混入日报或未来数据")
        elif req.basis == "night" and req.window.end.astimezone(now.tzinfo).hour == 6:
            req.rtu_energy_window = Window(start=req.window.start, end=req.window.end + timedelta(hours=1))
            if req.rtu_energy_window.end > now:
                raise ValueError("RTU 独立窗口尚未完成")
        # Reuse the shipped contract's day boundaries and 7/30-day validation.
        from lighting.results import LightingResult

        LightingResult.model_validate({
            "schema_version": "lighting-query/v1", "scene": req.scene,
            "status": "partial", "energy_view": req.energy_view,
            "query": {"id": "validate", "scope": req.scope, "timezone": req.timezone,
                      "window": req.window.model_dump(mode="json"), "cutoff": req.cutoff,
                      "generated_at": now, "basis": req.basis, "report_type": req.report_type,
                      "source": "照明只读服务", "coverage": "待查询"},
            "summary": "待查询", "columns": [{"key": "status", "label": "状态"}],
            "row_count": 0, "complete": False,
        })
        return req
