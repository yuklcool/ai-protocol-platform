"""Synthetic lighting evidence only. Never imported by production code."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from lighting.results import LAMP_REPORT, RTU_REPORT


def fixture(scene="night", view="night", *, query_id=None, status="success"):
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily = scene == "reconcile" or (scene == "energy" and view != "night")
    days = {"week": 7, "saving": 7, "volatility": 30}.get(view, 1) if scene == "energy" else 1
    start, end = (day - timedelta(days=days), day) if daily else (day - timedelta(hours=6), day + timedelta(hours=7))

    def stamp(value):
        return value.isoformat()

    query = {
        "id": query_id or uuid4().hex,
        "scope": "合成验收区域",
        "timezone": "Asia/Shanghai",
        "window": {"start": stamp(start), "end": stamp(end)},
        "cutoff": stamp(end),
        "generated_at": stamp(datetime.now(UTC)),
        "basis": "daily" if daily else "night",
        "report_type": "D" if daily else None,
        "source": "CI 合成 MCP fixture · 非生产数据",
        "coverage": "已返回 2/2 个合成对象,缺失项明确标注。",
        "filters": ["夜间与自然日分开", "缺失不补零", "报警事件数与去重设备数分开"],
        "missing": [],
    }

    def col(key, label, unit="", kind="text"):
        return {"key": key, "label": label, "unit": unit, "type": kind}

    rows = [
        {
            "id": "row-1",
            "lamp_id": "L-0348-A",
            "rtu_id": "RTU-017",
            "circuit_id": "2",
            "pole_id": "P-0348",
            "alarm_id": "alarm-001",
            "phase": "A",
            "anchor": stamp(start + timedelta(minutes=24)),
            "relationship_verified": True,
            "values": {
                "road": "合成滨河路",
                "alarm_type": "异常熄灯",
                "triggered_at": stamp(start + timedelta(minutes=24)),
                "restored_at": None,
                "history_complete": True,
                "minutes": 610,
                "watts": 150,
                "actual_kwh": 0.02,
                "count": 1,
                "date": start.date().isoformat(),
            },
            "evidence": [
                {
                    "label": "报警时点历史功率",
                    "value": 0,
                    "unit": "W",
                    "at": stamp(start + timedelta(minutes=24)),
                    "source": "合成历史巡测",
                    "note": "仅是历史读数,不能单凭 0 W 认定故障",
                },
                {
                    "label": "同回路核对",
                    "value": "尚需继续查询",
                    "unit": "",
                    "at": stamp(start + timedelta(minutes=24)),
                    "source": "合成历史归属",
                },
            ],
            "missing": [],
        },
        {
            "id": "row-2",
            "lamp_id": "L-0912-A",
            "rtu_id": "RTU-041",
            "circuit_id": "3",
            "pole_id": "P-0912",
            "alarm_id": "alarm-002",
            "phase": "B",
            "relationship_verified": False,
            "values": {
                "road": "合成文昌路",
                "alarm_type": "通信异常",
                "triggered_at": stamp(start + timedelta(hours=2)),
                "restored_at": stamp(start + timedelta(hours=3)),
                "history_complete": True,
                "minutes": None,
                "watts": 100,
                "actual_kwh": None,
                "count": 1,
                "date": start.date().isoformat(),
            },
            "evidence": [],
            "missing": ["尚未取得目标时点的历史电参"],
        },
    ]
    columns = [
        col("lamp_id", "单灯"),
        col("road", "道路"),
        col("rtu_id", "RTU"),
        col("circuit_id", "回路"),
        col("minutes", "亮灯分钟", "min", "number"),
        col("watts", "额定功率", "W", "number"),
        col("actual_kwh", "夜间能耗", "kWh", "number"),
        col("status_at_cutoff", "截止时点状态"),
    ]
    metrics = [
        {"label": "夜间有有效巡测", "value": 1, "unit": "盏", "note": "合成 1/2,有样本不等于整晚在线率"},
        {"label": "报警事件数", "value": 2, "unit": "条"},
        {"label": "去重单灯数", "value": 2, "unit": "盏"},
        {"label": "截止时点未解除", "value": 1, "unit": "条"},
    ]
    if scene == "lamp_alarms":
        columns = [
            col("lamp_id", "单灯"),
            col("road", "道路"),
            col("rtu_id", "RTU"),
            col("circuit_id", "回路"),
            col("alarm_type", "报警类型"),
            col("triggered_at", "触发时间", kind="time"),
            col("restored_at", "恢复时间", kind="time"),
            col("count", "触发次数", kind="number"),
            col("status_at_cutoff", "截止时点状态"),
        ]
    if scene == "rtu":
        columns = [
            col("rtu_id", "RTU"),
            col("name", "名称"),
            col("last_report", "最后历史上报", kind="time"),
            col("status", "判定时点状态"),
            col("circuits", "支路数", kind="number"),
            col("affected", "关联异常单灯", kind="number"),
        ]
        metrics = [
            {"label": "在管 RTU", "value": 2, "unit": "台"},
            {"label": "在线判定", "value": None, "note": "未取得生产判定配置"},
        ]
        query["source"] = "CI 合成 sl.r_his_coplog_phase · 非生产数据"
        for i, row in enumerate(rows):
            row["values"].update(
                name=f"合成控制箱 {i + 1}",
                last_report=stamp(end - timedelta(minutes=5)),
                status="判定配置待取得" if i == 0 else "窗口无记录",
                circuits=3,
                affected=None,
            )
    if scene == "rtu_alarms":
        columns = [
            col("rtu_id", "RTU"),
            col("alarm_type", "报警类型"),
            col("triggered_at", "发生时间", kind="time"),
            col("reading", "原始读数"),
            col("restored_at", "恢复时间", kind="time"),
            col("status_at_cutoff", "截止时点状态"),
        ]
        metrics = [{"label": "报警事件数", "value": 2, "unit": "条"}, {"label": "去重 RTU", "value": 2, "unit": "台"}]
        rows[0]["values"].update(alarm_type="漏电", reading="0.8 A", leakage_unit="A", trip_record=None)
        rows[1]["values"].update(alarm_type="过流", reading="12 A", actual_current=12, rated_current=None)
    if scene == "reconcile":
        columns = [
            col("date", "自然日"),
            col("rtu_id", "RTU"),
            col("poles", "灯杆数", kind="number"),
            col("lamps", "灯源数", kind="number"),
            col("lamp_kwh", "单灯合计", "kWh", "number"),
            col("rtu_kwh", "RTU 日报", "kWh", "number"),
            col("difference_kwh", "差额", "kWh", "number"),
            col("ratio", "有效比值", kind="number"),
            col("status", "状态"),
        ]
        for row in rows:
            row["values"].update(poles=1, lamps=2, lamp_kwh=20, rtu_kwh=0, lamp_filter_applied=True)
        rows[1]["values"]["rtu_kwh"] = None
        metrics = [
            {"label": "可比较倒挂 RTU", "value": 1, "unit": "台"},
            {"label": "缺少日报", "value": 1, "unit": "台"},
            {"label": "比值可计算", "value": 0, "unit": "台"},
        ]
    if scene == "energy":
        for i, row in enumerate(rows):
            row["values"].update(
                date=(day - timedelta(days=2 - i)).date().isoformat(),
                theoretical_kwh=100 if i == 0 else 900,
                actual_kwh=50 if i == 0 else 810,
                previous_kwh=10,
                previous_minutes=600,
                minutes=660,
                matched=i == 0,
                target_rate=None,
                recorded_rate=0,
            )
        columns = [col("date", "日期"), col("rtu_id", "RTU"), col("actual_kwh", "实际能耗", "kWh", "number")]
        if view == "night":
            columns += [
                col("previous_kwh", "前夜能耗", "kWh", "number"),
                col("minutes", "本夜亮灯分钟", "min", "number"),
                col("duration_kwh", "时长贡献", "kWh", "number"),
                col("other_kwh", "非时长贡献", "kWh", "number"),
            ]
        if view == "saving":
            columns += [
                col("theoretical_kwh", "理论能耗", "kWh", "number"),
                col("calculated_rate", "计算节能率", "ratio", "number"),
                col("recorded_rate", "系统记录值", "ratio", "number"),
                col("target_status", "目标核验"),
            ]
        if view == "volatility":
            columns += [
                col("previous_kwh", "前日能耗", "kWh", "number"),
                col("change_kwh", "变化量", "kWh", "number"),
                col("change_rate", "增幅", "ratio", "number"),
                col("increase_flag", "双阈值命中"),
            ]
        metrics = [{"label": "已返回对象", "value": 2, "unit": "个", "note": "合成样本,非全网结论"}]
    actions = [{"id": "retry", "label": "重新读取当前范围", "intent": "retry"}]
    if scene == "energy":
        actions += [
            {"id": f"energy-{key}", "label": label, "intent": "energy_view", "energy_view": key}
            for key, label in [
                ("night", "昨夜同窗口"),
                ("week", "近 7 日日报"),
                ("volatility", "30 日上升波动"),
                ("saving", "7 日节能率"),
            ]
        ]
    for row in rows:
        actions += [
            {"id": f"inspect-{row['id']}", "label": "查询单灯历史", "intent": "inspect_lamp", "row_id": row["id"]},
            {"id": f"circuit-{row['id']}", "label": "查询同回路证据", "intent": "compare_circuit", "row_id": row["id"]},
            {"id": f"rtu-{row['id']}", "label": "查询上游 RTU", "intent": "inspect_rtu", "row_id": row["id"]},
        ]
    chart = {
        "title": "合成能耗趋势" if scene == "energy" else "按小时报警事件分布",
        "x_key": "date",
        "x_label": "日期" if scene == "energy" else "小时",
        "y": [
            col(
                "value", "实际能耗" if scene == "energy" else "报警事件", "kWh" if scene == "energy" else "条", "number"
            )
        ],
        "rows": [
            {"date": row["values"]["date"], "value": row["values"]["actual_kwh"] if scene == "energy" else i + 1}
            for i, row in enumerate(rows)
        ],
        "filter_key": "date",
    }
    report = (
        [
            {"title": title, "content": "CI 合成章节。未提供的业务字段保持待取得,不冒充生产报告。"}
            for title in (RTU_REPORT if scene == "rtu" else LAMP_REPORT)
        ]
        if scene in {"night", "lamp_alarms", "rtu"}
        else []
    )
    result = {
        "schema_version": "lighting-query/v1",
        "scene": scene,
        "status": status,
        "query": query,
        "summary": "合成验收结论: 先核对未解除报警,历史证据缺口需要继续补查。",
        "energy_view": view if scene == "energy" else None,
        "metrics": metrics,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "complete": True,
        "actions": actions,
        "chart": chart if scene != "reconcile" else None,
        "report": report,
    }
    if status == "error":
        result["error"] = "合成数据源暂不可用"
    if status == "empty":
        result.update(rows=[], row_count=0, chart=None, metrics=[], report=[], actions=[])
        result["query"]["coverage"] = "当前合成范围没有记录。"
    return result
