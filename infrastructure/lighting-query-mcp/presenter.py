"""Project the SQL service's facts into the shipped lighting-query/v1 model."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid

from lighting.results import LAMP_REPORT, RTU_REPORT, LightingResult, normalize
from request import LightingRequest

HISTORY_GAP = "报警表保留当前处理状态,尚未确认完整触发/恢复事件流水;截止时点恢复状态与独立事件数不能可靠还原。"
RELATION_GAP = "下挂关系来自当前台账,未取得历史变更记录;不据此认定历史归属或启用跨层级追查。"
SAMPLE_GAP = "夜间能耗和时长仅用窗口内有效巡测累计读数差,首末样本之间的观测区间不等于完整开关灯周期;复位、缺测或不足两点留空。"


def column(key, label, unit="", kind="text"):
    return {"key": key, "label": label, "unit": unit, "type": kind}


def metric(label, value, unit="", note=""):
    return {"label": label, "value": value, "unit": unit, "note": note}


def timestamp(value):
    if value is None:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return dt.isoformat()


def table(items, fields):
    if not items:
        return "当前查询未返回记录,不能据此判断无异常。"
    def text(value):
        return "未取得" if value is None else str(value).replace("|", "\\|").replace("\n", " ")
    return "|" + "|".join(label for _, label in fields) + "|\n|" + "|".join("---" for _ in fields) + "|\n" + "\n".join(
        "|" + "|".join(text(item.get(key)) for key, _ in fields) + "|" for item in items)


def report(req, data, alarm_data):
    rtu = req.scene == "rtu"
    titles = RTU_REPORT if rtu else LAMP_REPORT
    totals, alarms = data["totals"], alarm_data["totals"]
    samples = data["rows"]
    head = f"范围：{req.scope}。时间：{req.window.start.isoformat()} 至 {req.window.end.isoformat()}。"
    overview = f"报警记录：{alarms['objects']} 条；涉及去重对象：{alarms['devices']}。独立事件、已解除及未解除数量暂不可确认。\n\n{HISTORY_GAP}"
    types = table(alarms.get("types"), [("alarm_type", "报警类型"), ("count", "记录数")])
    hours = table(alarms.get("hours"), [("hour", "时段"), ("count", "记录数")])
    focus = table(alarm_data["rows"][:20], [("rtu_code" if rtu else "lamp_code", "RTU编号" if rtu else "单灯标识"), ("alarm_type", "报警类型"), ("triggered_at", "发生时间"), ("last_trigger", "最后发生时间")])
    state = f"本次截止为 {req.cutoff.isoformat()},章节固定名称不改变本次实际截止时点。纳入对象：{totals['objects']}；窗口内有历史巡测：{totals['observed']}。\n\n在线/离线数量：未取得已确认的生产判定配置。白天零值不能单独认定故障。"
    advice = "先核查报警集中时段与计划边界,再按道路/对象复核历史电参；漏电类交维护人员优先核验保护与现场状况。均为建议,未执行控制、消警或派单。"
    if rtu:
        contents = [head + f"\n\n取得 {totals['observed']}/{totals['objects']} 台历史巡测。在线判定及根因仍需补证据。",
                    overview, types, hours + "\n\n### 时间观察\n按本次实际记录分布观察,不从集中时段直接推定根因。",
                    focus + "\n\n### 重点对象判断\n重点清单为本次已返回记录,不将重复记录直接等同独立事件。",
                    state + "\n\n### 口径说明（重要）\n历史巡测末次样本不等于当前在线,未配置过期阈值。\n\n### 巡测异常样本（部分）\n" + table(samples[:20], [("rtu_code", "RTU编号"), ("last_report", "末次历史上报"), ("status", "状态")]), advice]
    else:
        energy = f"有效巡测区间能耗合计：{totals.get('actual_kwh')} kWh；有效能耗对象：{totals.get('valid_energy')}。\n\n{SAMPLE_GAP}\n\n### 能耗分布\n" + table(samples[:20], [("lamp_code", "单灯"), ("actual_kwh", "观测区间kWh"), ("minutes", "观测分钟"), ("rated_power", "额定功率W")]) + "\n\n### 能耗判断\n长时低耗仅为线索,高低能耗不能单独认定故障或节能。"
        contents = [head + f"\n\n取得 {totals['observed']}/{totals['objects']} 个对象的历史巡测；证据缺口见以下章节。",
                    overview, types, hours,
                    table(alarms.get("roads"), [("road", "道路"), ("count", "报警记录数")]) + "\n\n### 道路观察\n范围统计独立计算,不由截断清单推算。",
                    focus + "\n\n### 未解除报警重点清单\n历史恢复过程未确认,暂不能可靠列出。\n\n### 重点对象判断\n单灯原因需同窗口及同回路证据,当前不直接定性。",
                    state + "\n\n### 运行判断\n有样本覆盖不叫整晚在线率,没有样本不直接叫通信故障。", energy, advice]
    return [{"title": title, "content": body} for title, body in zip(titles, contents, strict=True)]


def present(req: LightingRequest, data: dict, now: datetime, alarm_data: dict | None = None) -> dict:
    totals = data["totals"]
    count = data["row_count"]
    complete = count == len(data["rows"])
    rows, actions, metrics, columns, missing = [], [], [], [], []
    chart = None
    for record in data["rows"]:
        values = dict(record)
        for key in ("triggered_at", "last_trigger", "recorded_conduct_at", "sample_at", "last_report", "first_sample", "last_sample"):
            if key in values:
                values[key] = timestamp(values[key])
        row = {"id": str(values.pop("id")), "values": values, "evidence": [], "missing": [], "relationship_verified": False}
        if req.scene == "night" or (req.scene == "energy" and req.energy_view == "night"):
            row["lamp_id"] = row["id"]
            row["missing"] = [RELATION_GAP, SAMPLE_GAP]
            row["evidence"] = [
                {"label": label, "value": values.get(key), "unit": unit, "source": "单灯历史巡测", "at": values.get("last_sample"), "note": "末次实际观测,未冒充截止时点新采样"}
                for key, label, unit in [("voltage", "电压", "V"), ("power", "有功功率", "W"), ("observed_online", "记录在线值", ""), ("observed_on", "记录开灯值", "")]
            ]
            actions.append({"id": "lamp-" + str(len(rows)), "label": "查询此灯历史证据", "intent": "inspect_lamp", "row_id": row["id"]})
            row["anchor"] = values.get("last_sample")
        elif req.scene in {"lamp_alarms", "rtu_alarms"}:
            row["alarm_id"] = row["id"]
            row["lamp_id"] = values.pop("lamp_id", None)
            row["rtu_id"] = values.pop("rtu_id", None)
            values.update(history_complete=False, restored_at=None)
            row["anchor"] = values["triggered_at"]
            row["missing"] = [HISTORY_GAP]
            row["evidence"] = [{"label": "源记录处理状态码", "value": values.get("recorded_state"), "source": "报警记录", "note": "业务处理状态,不能自动当作历史恢复证明"}]
            if req.scene == "rtu_alarms":
                name = values.get("alarm_type") or "未取得类型"
                values["alarm_type"] = next((kind for kind, words in [("漏电", ["漏电"]), ("缺相", ["缺相"]), ("过流", ["过流", "过电流"]), ("断路", ["断路"])] if any(word in name for word in words)), name)
                values["recorded_alarm_name"] = name
                # Do not interpret packed channels or their units without a verified mapping.
                values["reading"] = values.get("raw_leakage")
                for phase in "abc":
                    for key, label, unit in [(f"voltage_{phase}", f"{phase.upper()}相电压", "V"), (f"current_{phase}", f"{phase.upper()}相电流", "A")]:
                        valid = values.get("sample_success") == 1
                        row["evidence"].append({"label": label, "value": values.get(key) if valid else None, "unit": unit, "at": values.get("sample_at"), "source": "报警关联的RTU历史巡测", "note": "仅成功采样有效,没有采样不补零"})
                row["missing"].append("相位/支路映射、原始漏电单位及保护动作证据尚未确认。")
                actions.append({"id": "alarm-" + str(len(rows)), "label": "核查此报警历史证据", "intent": "inspect_rtu_alarm", "row_id": row["id"]})
            elif row["lamp_id"]:
                actions.append({"id": "alarm-lamp-" + str(len(rows)), "label": "查询此灯历史证据", "intent": "inspect_lamp", "row_id": row["id"]})
        elif req.scene == "rtu":
            row["rtu_id"] = row["id"]
            row["anchor"] = values.get("last_report")
            row["missing"] = ["未取得系统在线过期阈值,不计算在线率。"]
            for phase in "abc":
                for key, label, unit in [(f"voltage_{phase}", f"{phase.upper()}相电压", "V"), (f"current_{phase}", f"{phase.upper()}相电流", "A")]:
                    row["evidence"].append({"label": label, "value": values.get(key) if values.get("is_succeeded") == 1 else None, "unit": unit, "at": values.get("last_report"), "source": "RTU历史巡测", "note": "末次历史样本,采集失败不使用原始电参判断"})
        elif req.scene == "reconcile":
            row["rtu_id"] = values.pop("rtu_id")
            row["missing"] = [RELATION_GAP]
            values["lamp_filter_applied"] = True
        else:
            row["rtu_id"] = values.pop("rtu_id", None)
            if values.get("actual_kwh") is None:
                row["missing"].append("日报重复、缺失或超出有效值范围,不补零。")
            if req.energy_view == "saving":
                row["missing"].append("未取得目标节能率,不能判定是否达标。")
                if values.get("source_records") != 1:
                    row["missing"].append("同日存在多个全系统指标记录,不擅自挑选或重复相加。")
        rows.append(row)
    if req.scene == "night" or (req.scene == "energy" and req.energy_view == "night"):
        columns = [column("lamp_code", "单灯"), column("pole", "灯杆"), column("road", "道路"), column("rtu_code", "当前台账RTU"), column("alarms", "报警记录数", kind="number"), column("minutes", "观测亮灯分钟", "min", "number"), column("actual_kwh", "观测区间能耗", "kWh", "number"), column("rated_power", "额定功率", "W", "number"), column("status", "巡测覆盖")]
        metrics = [metric("纳入单灯", totals["objects"], "盏"), metric("夜间有样本", totals["observed"], "盏", "不是整晚在线率"), metric("有效巡测区间能耗", totals.get("actual_kwh"), "kWh", SAMPLE_GAP), metric("能耗有效对象", totals["valid_energy"], "盏")]
        missing = [SAMPLE_GAP, RELATION_GAP, HISTORY_GAP, "当前夜间能耗为单灯观测区间值；尚未取得RTU完整夜间能耗,独立RTU窗口仅保留查询口径。"]
        if req.scene == "energy":
            columns.extend([column("previous_kwh", "前夜观测能耗", "kWh", "number"), column("duration_kwh", "时长贡献", "kWh", "number"), column("other_kwh", "其他贡献", "kWh", "number")])
    elif req.scene in {"lamp_alarms", "rtu_alarms"}:
        columns = [column("rtu_code" if req.scene == "rtu_alarms" else "lamp_code", "RTU" if req.scene == "rtu_alarms" else "单灯"), column("alarm_type", "报警类型"), column("triggered_at", "首次发生", kind="time"), column("last_trigger", "末次发生", kind="time"), column("recorded_conduct_at", "源记录处理时刻", kind="time"), column("status_at_cutoff", "截止时点状态")]
        metrics = [metric("报警记录数", count, "条", "不是已验证独立事件数"), metric("受影响去重对象", totals["devices"]), metric("截止时点未解除", None, "条", HISTORY_GAP)]
        missing = [HISTORY_GAP]
        chart = {"title": "报警记录按小时分布", "x_key": "hour", "x_label": "时段", "y": [column("count", "记录数", "条", "number")], "rows": totals.get("hours") or []}
    elif req.scene == "rtu":
        columns = [column("rtu_code", "RTU编号"), column("name", "RTU名称"), column("last_report", "最后历史上报", kind="time"), column("status", "状态"), column("circuits", "当前台账回路数", kind="number")]
        metrics = [metric("纳入RTU", count, "台"), metric("窗口有历史上报", totals["observed"], "台"), metric("在线数", None, "台", "未取得生产阈值")]
        missing = ["未取得生产在线判定配置；未取得历史下挂关系,不能推算影响灯数。", HISTORY_GAP]
    elif req.scene == "reconcile":
        columns = [column("date", "日期"), column("rtu_code", "RTU编号"), column("name", "名称"), column("poles", "有效灯杆数", kind="number"), column("lamps", "有效灯源数", kind="number"), column("lamp_kwh", "单灯合计", "kWh", "number"), column("rtu_kwh", "RTU日报", "kWh", "number"), column("ledger_difference_kwh", "当前台账映射差额", "kWh", "number"), column("difference_kwh", "已验证历史差额", "kWh", "number"), column("ratio", "已验证比值", kind="number"), column("status", "结论")]
        metrics = [metric("RTU日期组合", count), metric("有有效RTU日报", totals["rtu_reports"]), metric("有有效单灯日报", totals["lamp_reports"]), metric("已验证倒挂数", None, note=RELATION_GAP)]
        missing = [RELATION_GAP, "日报重复记录按无效处理；同一灯有多个RTU映射时剔除,不将不确定关系重复累计。"]
    else:
        columns = [column("date", "日期"), column("actual_kwh", "实际能耗", "kWh", "number")]
        if req.energy_view == "saving":
            columns.extend([column("theoretical_kwh", "理论能耗", "kWh", "number"), column("calculated_rate", "核算节能率", "ratio", "number"), column("recorded_rate", "系统记录率", "ratio", "number"), column("target_status", "目标核验"), column("rate_consistency", "一致性")])
        else:
            columns.insert(1, column("rtu_code", "RTU编号"))
            columns.insert(2, column("name", "名称"))
            if req.energy_view == "volatility":
                columns.extend([column("previous_kwh", "前一日", "kWh", "number"), column("change_kwh", "增加量", "kWh", "number"), column("change_rate", "增加率", "ratio", "number"), column("increase_flag", "命中双阈值")])
        metrics = [metric("日报记录组合", count), metric("有效能耗记录", totals["valid_energy"]), metric("有效记录能耗合计", totals.get("actual_kwh"), "kWh", "只统计实际存在的有效日报,缺测不补零")]
        days = {d["date"]: d["actual_kwh"] for d in totals.get("days") or []}
        start_day = req.window.start.astimezone(ZoneInfo(req.timezone)).date()
        end_day = req.window.end.astimezone(ZoneInfo(req.timezone)).date()
        chart_rows = [{"date": (start_day + timedelta(days=i)).isoformat(), "actual_kwh": days.get((start_day + timedelta(days=i)).isoformat())} for i in range((end_day-start_day).days)]
        chart = {"title": "有效日报能耗趋势", "x_key": "date", "x_label": "自然日", "y": [column("actual_kwh", "能耗", "kWh", "number")], "rows": chart_rows, "filter_key": "date"}
        if req.energy_view == "volatility":
            metrics.append(metric("命中上升双阈值", totals.get("increases"), "个日期点", "同时增加≥50kWh且≥30%,前日非零且为相邻自然日"))
        missing = ["趋势仅汇总已取得的有效日报；设备日报覆盖不足时不能称为完整全网用电量。"]
    if req.scene == "energy" and not req.device.lamp_id and req.scope == "全系统":
        actions.extend({"id": "energy-" + view, "label": label, "intent": "energy_view", "energy_view": view} for view, label in [("night", "昨夜同窗口"), ("week", "7日日报"), ("volatility", "30日上升波动"), ("saving", "7日节能率")] if view != req.energy_view)
    query = {"id": uuid.uuid4().hex, "scope": req.scope, "timezone": req.timezone,
             "window": req.window.model_dump(mode="json"), "cutoff": req.cutoff,
             "generated_at": now, "basis": req.basis, "report_type": req.report_type,
             "rtu_energy_window": req.rtu_energy_window.model_dump(mode="json") if req.rtu_energy_window else None,
             "source": "授权照明数据库·固定只读查询", "coverage": f"范围内共 {count} 个对象/记录组合,返回 {len(rows)} 个；清单截断不影响独立范围统计。",
             "filters": ["只读；不执行控制、消警、写库或派单", "日报仅D；单灯逐条0≤kWh<100；RTU逐条0≤kWh<1500；重复日报留空"], "missing": missing}
    summary = f"本次范围 {req.scope},取得 {count} 个对象/记录组合。请优先查看实际证据和缺口,不将缺测、未知状态或当前台账当作历史正常证明。"
    result = {"schema_version": "lighting-query/v1", "scene": req.scene, "status": "partial", "energy_view": req.energy_view,
              "query": query, "summary": summary, "metrics": metrics, "columns": columns,
              "rows": rows, "row_count": count, "complete": complete, "chart": chart, "actions": actions,
              "report": report(req, data, alarm_data) if alarm_data and req.scene in {"night", "rtu"} else []}
    normalized = normalize(LightingResult.model_validate(result))
    if count == 0:
        normalized.status = "empty"
        normalized.summary = "本次范围没有取得记录,不能据此判断没有异常；请检查查询范围、时间和数据覆盖。"
    return normalized.model_dump(mode="json")
