"""Fixed PostgreSQL reads, mapped from the server's lighting Skills.

Only literals are substituted. Identifiers, joins and calculations stay here.
Every bounded list has an independent population count and aggregate block.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from request import LightingRequest


def literal(value: str) -> str:
    if "\x00" in value or "\\" in value:
        raise ValueError("查询条件含无效字符")
    return "'" + value.replace("'", "''") + "'"


def stamp(value) -> str:
    return "TIMESTAMP " + literal(value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat())


def envelope(sql: str, limit: int, aggregates: str = "COUNT(*) AS objects", order: str = "id") -> str:
    return f"""WITH data AS ({sql}), totals AS (SELECT {aggregates} FROM data)
SELECT json_build_object(
 'rows', COALESCE((SELECT json_agg(t) FROM (SELECT * FROM data ORDER BY {order} LIMIT {limit}) t), '[]'::json),
 'row_count', (SELECT COUNT(*) FROM data),
 'totals', (SELECT row_to_json(totals) FROM totals)) AS payload"""


def scope_query(req: LightingRequest) -> str | None:
    if req.scope == "全系统":
        return None
    q = literal(req.scope)
    sql = f"SELECT 'rtu_'||rtu_id AS id FROM sl.r_rtu WHERE rtu_code={q} OR rtu_name={q}"
    if req.scene in {"night", "lamp_alarms"} or (req.scene == "energy" and req.energy_view == "night"):
        sql += f" UNION SELECT 'street_'||street_id FROM sl.b_street WHERE street_name={q}"
        sql += f" UNION SELECT 'lamp_'||alone_lamp_id FROM sl.l_alonelamp WHERE alone_lamp_code={q}"
        sql += f" UNION SELECT 'pole_'||lamp_post_id FROM sl.l_lamppost WHERE lamp_post_code={q}"
    return envelope(sql, 2)


LAMP_JOINS = """FROM sl.l_alonelamp l
LEFT JOIN sl.l_lamppost p ON p.lamp_post_id=l.lamp_post_id
LEFT JOIN sl.b_street s ON s.street_id=p.street_id
LEFT JOIN sl.r_rturoad c ON c.rturoad_id=l.rtu_road_id
LEFT JOIN sl.r_road_switch sw ON sw.road_switch_id=c.road_switch_id
LEFT JOIN sl.r_rtu r ON r.control_cabinet_id=sw.control_cabinet_id"""


def lamp_scope(req: LightingRequest) -> str:
    parts = []
    if req.scope != "全系统":
        q = literal(req.scope)
        parts.append(f"(r.rtu_code={q} OR r.rtu_name={q} OR s.street_name={q} OR l.alone_lamp_code={q} OR p.lamp_post_code={q})")
    if req.device.lamp_id:
        parts.append("l.alone_lamp_id=" + literal(req.device.lamp_id))
    if req.device.rtu_id:
        parts.append("r.rtu_id=" + literal(req.device.rtu_id))
    return " AND ".join(parts) or "TRUE"


def rtu_scope(req: LightingRequest) -> str:
    parts = []
    if req.scope != "全系统":
        q = literal(req.scope)
        parts.append(f"(r.rtu_code={q} OR r.rtu_name={q})")
    if req.device.rtu_id:
        parts.append("r.rtu_id=" + literal(req.device.rtu_id))
    return " AND ".join(parts) or "TRUE"


def lamp_samples(req: LightingRequest) -> str:
    start, end = stamp(req.window.start), stamp(req.window.end)
    before, before_end = stamp(req.window.start - timedelta(days=1)), stamp(req.window.end - timedelta(days=1))
    # Restrict lamp aggregation before joins so ledger ambiguity cannot multiply observations.
    return f"""WITH assets AS (
 SELECT l.alone_lamp_id AS id, MIN(l.alone_lamp_code) AS lamp_code,
 MIN(p.lamp_post_code) AS pole, MIN(s.street_name) AS road, MIN(l.lamp_power) AS rated_power,
 MIN(r.rtu_code) AS rtu_code, MIN(c.rturoad_name) AS circuit,
 COUNT(DISTINCT r.rtu_id) AS ledger_rtu_matches
 {LAMP_JOINS} WHERE {lamp_scope(req)} GROUP BY l.alone_lamp_id
), samples AS (
 SELECT h.*, CASE WHEN h.cop_date>={start} THEN 1 ELSE 0 END AS period,
 LAG(h.energy) OVER (PARTITION BY h.alone_lamp_id, (h.cop_date>={start}) ORDER BY h.cop_date,h.his_coplog_id) AS previous_energy,
 LAG(h.light_time) OVER (PARTITION BY h.alone_lamp_id, (h.cop_date>={start}) ORDER BY h.cop_date,h.his_coplog_id) AS previous_light_time
 FROM sl.l_his_coplog h JOIN assets a ON a.id=h.alone_lamp_id
 WHERE (h.cop_date>={start} AND h.cop_date<={end}) OR (h.cop_date>={before} AND h.cop_date<={before_end})
), stats AS (
 SELECT alone_lamp_id,period,COUNT(*) AS samples,MIN(cop_date) AS first_sample,MAX(cop_date) AS last_sample,
 CASE WHEN COUNT(energy)>=2 AND NOT BOOL_OR(energy<previous_energy)
 THEN MAX(energy)-MIN(energy) END AS actual_kwh,
 CASE WHEN COUNT(light_time)>=2 AND NOT BOOL_OR(light_time<previous_light_time)
 THEN MAX(light_time)-MIN(light_time) END AS minutes,
 (ARRAY_AGG(voltage ORDER BY cop_date DESC,his_coplog_id DESC))[1] AS voltage,
 (ARRAY_AGG(active_power ORDER BY cop_date DESC,his_coplog_id DESC))[1] AS power,
 (ARRAY_AGG(is_online ORDER BY cop_date DESC,his_coplog_id DESC))[1] AS observed_online,
 (ARRAY_AGG(is_switch_on ORDER BY cop_date DESC,his_coplog_id DESC))[1] AS observed_on
 FROM samples GROUP BY alone_lamp_id,period
), alarms AS (
 SELECT alone_lamp_id,COUNT(*) AS alarms FROM sl.l_his_hitch_alarm
 WHERE alarm_add_date>={start} AND alarm_add_date<={end} GROUP BY alone_lamp_id
)
SELECT a.*, n.samples,n.first_sample,n.last_sample,n.actual_kwh,n.minutes,n.voltage,n.power,
 n.observed_online,n.observed_on,old.actual_kwh AS previous_kwh,old.minutes AS previous_minutes,
 (n.actual_kwh IS NOT NULL AND old.actual_kwh IS NOT NULL AND old.minutes>0) AS matched,
 COALESCE(h.alarms,0) AS alarms,
 CASE WHEN n.samples IS NULL THEN '窗口无记录' ELSE '有历史巡测,在线判定待核' END AS status
FROM assets a LEFT JOIN stats n ON n.alone_lamp_id=a.id AND n.period=1
LEFT JOIN stats old ON old.alone_lamp_id=a.id AND old.period=0
LEFT JOIN alarms h ON h.alone_lamp_id=a.id"""


def alarms(req: LightingRequest, rtu: bool) -> str:
    start, end = stamp(req.window.start), stamp(req.window.end)
    extra = " AND h." + ("hitch_alarm_id" if rtu else "his_hitch_alarm_id") + "=" + literal(req.device.alarm_id) if req.device.alarm_id else ""
    if rtu:
        return f"""SELECT h.hitch_alarm_id AS id,h.rtu_id,r.rtu_code,r.rtu_name AS name,
 d.hitch_name AS alarm_type,h.occur_date AS triggered_at,h.conduct_date AS recorded_conduct_at,
 h.conduct_statue AS recorded_state,h.last_date AS last_trigger,h.alarmlevel,
 h.hitch_intro AS recorded_description,h.relay_leak_currents AS raw_leakage,
 p.cop_date AS sample_at,p.is_succeeded AS sample_success,
 p.rtu_scale_u1 AS voltage_a,p.rtu_scale_u2 AS voltage_b,p.rtu_scale_u3 AS voltage_c,
 p.rtu_scale_isp1 AS current_a,p.rtu_scale_isp2 AS current_b,p.rtu_scale_isp3 AS current_c
 FROM sl.r_his_hitch_alarm h JOIN sl.r_rtu r ON r.rtu_id=h.rtu_id
 LEFT JOIN sl.b_hitch_dic d ON d.hitch_dic_id=h.hitch_dic_id
 LEFT JOIN sl.r_his_coplog_phase p ON p.coplog_phase_id=h.coplog_phase_id AND p.rtu_id=h.rtu_id
 WHERE h.occur_date>={start} AND h.occur_date<={end} AND {rtu_scope(req)}{extra}"""
    return f"""SELECT h.his_hitch_alarm_id AS id,h.alone_lamp_id AS lamp_id,
 l.alone_lamp_code AS lamp_code,p.lamp_post_code AS pole,s.street_name AS road,
 d.hitch_name AS alarm_type,h.alarm_add_date AS triggered_at,h.last_date AS last_trigger,
 h.conduct_date AS recorded_conduct_at,h.alarm_state AS recorded_state,
 h.voltage,h.leakage_current,h.hitch_intro AS recorded_description
 FROM sl.l_his_hitch_alarm h
 LEFT JOIN sl.l_alonelamp l ON l.alone_lamp_id=h.alone_lamp_id
 LEFT JOIN sl.l_lamppost p ON p.lamp_post_id=h.lamp_post_id
 LEFT JOIN sl.b_street s ON s.street_id=h.street_id
 LEFT JOIN sl.b_hitch_dic d ON d.hitch_dic_id=h.hitch_dic_id
 WHERE h.alarm_add_date>={start} AND h.alarm_add_date<={end}
 {('AND h.alone_lamp_id=' + literal(req.device.lamp_id)) if req.device.lamp_id else ''}{extra}"""


def lamp_alarms(req: LightingRequest) -> str:
    # Scope by a deduplicated asset subquery; do not multiply alarm rows by ledger joins.
    plain = req.model_copy(deep=True)
    plain.scope = "全系统"
    plain.device.rtu_id = None
    sql = alarms(plain, False)
    if req.scope != "全系统" or req.device.rtu_id:
        sql += f" AND h.alone_lamp_id IN (SELECT l.alone_lamp_id {LAMP_JOINS} WHERE {lamp_scope(req)})"
    return sql


def rtu_samples(req: LightingRequest) -> str:
    start, end = stamp(req.window.start), stamp(req.window.end)
    return f"""SELECT r.rtu_id AS id,r.rtu_code,r.rtu_name AS name,
 p.cop_date AS last_report,p.is_succeeded,p.rtu_scale_u1 AS voltage_a,p.rtu_scale_u2 AS voltage_b,
 p.rtu_scale_u3 AS voltage_c,p.rtu_scale_isp1 AS current_a,p.rtu_scale_isp2 AS current_b,
 p.rtu_scale_isp3 AS current_c,
 (SELECT COUNT(DISTINCT c.rturoad_id) FROM sl.r_road_switch sw JOIN sl.r_rturoad c ON c.road_switch_id=sw.road_switch_id
 WHERE sw.control_cabinet_id=r.control_cabinet_id) AS circuits,
 CASE WHEN p.cop_date IS NULL THEN '窗口无记录' WHEN p.is_succeeded=0 THEN '末次巡测失败'
 ELSE '有历史上报,在线阈值待核' END AS status
 FROM sl.r_rtu r LEFT JOIN LATERAL (
 SELECT * FROM sl.r_his_coplog_phase h WHERE h.rtu_id=r.rtu_id AND h.cop_date>={start}
 AND h.cop_date<={end} ORDER BY h.cop_date DESC,h.coplog_phase_id DESC LIMIT 1) p ON TRUE
 WHERE {rtu_scope(req)}"""


def daily_energy(req: LightingRequest) -> str:
    start = req.window.start.astimezone(ZoneInfo(req.timezone)).date()
    end = req.window.end.astimezone(ZoneInfo(req.timezone)).date()
    if req.energy_view == "saving":
        if req.scope != "全系统" or req.device.rtu_id:
            raise ValueError("固定节能率只支持全系统范围,不能把全系统指标当作设备指标")
        return f"""SELECT report_date::text AS id,report_date::text AS date,
 CASE WHEN COUNT(*)=1 THEN MAX(theory_elect_degree) END AS theoretical_kwh,
 CASE WHEN COUNT(*)=1 THEN MAX(real_elect_degree) END AS actual_kwh,
 CASE WHEN COUNT(*)=1 THEN MAX(energy_saving_rate) END AS recorded_rate,
 CASE WHEN COUNT(*)=1 THEN MAX(save_elect_degree) END AS recorded_saving,
 COUNT(*) AS source_records
 FROM sl.energy_saving_rate WHERE report_date>={literal(str(start))}::date
 AND report_date<{literal(str(end))}::date AND date_type='D' AND report_type='total'
 GROUP BY report_date"""
    first = start - timedelta(days=1) if req.energy_view == "volatility" else start
    return f"""WITH daily AS (
 SELECT e.rtu_id,LEFT(e.read_date_time,10) AS date,r.rtu_code,r.rtu_name AS name,
 CASE WHEN COUNT(*)=1 AND MIN(e.all_electric_energy)>=0 AND MAX(e.all_electric_energy)<1500
 THEN MAX(e.all_electric_energy) END AS actual_kwh,
 COUNT(*) AS source_records
 FROM sl.r_energy_report e JOIN sl.r_rtu r ON r.rtu_id=e.rtu_id
 WHERE e.report_type='D' AND e.read_date_time>={literal(str(first))}
 AND e.read_date_time<{literal(str(end))} AND {rtu_scope(req)}
 GROUP BY e.rtu_id,LEFT(e.read_date_time,10),r.rtu_code,r.rtu_name
), paired AS (
 SELECT d.*, old.actual_kwh AS previous_kwh FROM daily d
 LEFT JOIN daily old ON old.rtu_id=d.rtu_id AND old.date=(d.date::date-1)::text
)
SELECT rtu_id||'_'||date AS id,* FROM paired WHERE date>={literal(str(start))}"""


def reconcile(req: LightingRequest) -> str:
    start = literal(str(req.window.start.astimezone(ZoneInfo(req.timezone)).date()))
    end = literal(str(req.window.end.astimezone(ZoneInfo(req.timezone)).date()))
    return f"""WITH mapping AS (
 SELECT l.alone_lamp_id,MIN(l.lamp_post_id) AS pole_id,MIN(r.rtu_id) AS rtu_id,
 COUNT(DISTINCT r.rtu_id) AS matches
 {LAMP_JOINS} WHERE {lamp_scope(req)} GROUP BY l.alone_lamp_id
), lamps AS (
 SELECT e.alone_lamp_id,LEFT(e.read_date_time,10) AS date,
 CASE WHEN COUNT(*)=1 AND MIN(e.all_electric_energy)>=0 AND MAX(e.all_electric_energy)<100
 THEN MAX(e.all_electric_energy) END AS kwh
 FROM sl.l_energy_report e WHERE e.report_type='D'
 AND e.read_date_time>={start} AND e.read_date_time<{end} GROUP BY e.alone_lamp_id,LEFT(e.read_date_time,10)
), lamp_totals AS (
 SELECT m.rtu_id,e.date,SUM(e.kwh) AS lamp_kwh,
 COUNT(DISTINCT m.pole_id) FILTER(WHERE e.kwh IS NOT NULL) AS poles,
 COUNT(*) FILTER(WHERE e.kwh IS NOT NULL) AS lamps,
 COUNT(*) FILTER(WHERE e.kwh IS NULL) AS invalid_lamps
 FROM lamps e JOIN mapping m ON m.alone_lamp_id=e.alone_lamp_id AND m.matches=1
 GROUP BY m.rtu_id,e.date
), rtus AS (
 SELECT rtu_id,LEFT(read_date_time,10) AS date,
 CASE WHEN COUNT(*)=1 AND MIN(all_electric_energy)>=0 AND MAX(all_electric_energy)<1500
 THEN MAX(all_electric_energy) END AS rtu_kwh,COUNT(*) AS source_records
 FROM sl.r_energy_report WHERE report_type='D' AND read_date_time>={start} AND read_date_time<{end}
 GROUP BY rtu_id,LEFT(read_date_time,10)
), days AS (
 SELECT generate_series({start}::timestamp,{end}::timestamp-INTERVAL '1 day',INTERVAL '1 day')::date::text AS date
)
SELECT r.rtu_id||'_'||d.date AS id,r.rtu_id,r.rtu_code,r.rtu_name AS name,d.date,
 l.poles,l.lamps,l.lamp_kwh,l.invalid_lamps,t.rtu_kwh,t.source_records,
 l.lamp_kwh-t.rtu_kwh AS ledger_difference_kwh
 FROM sl.r_rtu r CROSS JOIN days d
 LEFT JOIN lamp_totals l ON l.rtu_id=r.rtu_id AND l.date=d.date
 LEFT JOIN rtus t ON t.rtu_id=r.rtu_id AND t.date=d.date WHERE {rtu_scope(req)}"""


def build_query(req: LightingRequest) -> str:
    if req.scene == "night" or (req.scene == "energy" and req.energy_view == "night"):
        return envelope(lamp_samples(req), req.limit,
                        "COUNT(*) AS objects,COUNT(samples) AS observed,SUM(actual_kwh) AS actual_kwh,COUNT(actual_kwh) AS valid_energy,SUM(alarms) AS alarms",
                        "alarms DESC,id")
    if req.scene in {"lamp_alarms", "rtu_alarms"}:
        rtu = req.scene == "rtu_alarms"
        sql = alarms(req, True) if rtu else lamp_alarms(req)
        distributions = """,(SELECT json_agg(x) FROM (SELECT alarm_type,COUNT(*) AS count FROM data GROUP BY alarm_type ORDER BY count DESC) x) AS types,
        (SELECT json_agg(x) FROM (SELECT TO_CHAR(triggered_at,'YYYY-MM-DD HH24:00') AS hour,COUNT(*) AS count FROM data GROUP BY hour ORDER BY hour) x) AS hours"""
        if not rtu:
            distributions += ",(SELECT json_agg(x) FROM (SELECT road,COUNT(*) AS count FROM data GROUP BY road ORDER BY count DESC LIMIT 10) x) AS roads"
        return envelope(sql, req.limit, "COUNT(*) AS objects,COUNT(DISTINCT " + ("rtu_id" if rtu else "lamp_id") + ") AS devices" + distributions, "triggered_at DESC,id")
    if req.scene == "rtu":
        return envelope(rtu_samples(req), req.limit, "COUNT(*) AS objects,COUNT(last_report) AS observed", "last_report ASC NULLS FIRST,id")
    if req.scene == "reconcile":
        return envelope(reconcile(req), req.limit, "COUNT(*) AS objects,COUNT(rtu_kwh) AS rtu_reports,COUNT(lamp_kwh) AS lamp_reports", "ledger_difference_kwh DESC NULLS LAST,id")
    extra = ",COUNT(*) FILTER(WHERE previous_kwh>0 AND actual_kwh-previous_kwh>=50 AND (actual_kwh-previous_kwh)/previous_kwh>=0.3) AS increases" if req.energy_view == "volatility" else ""
    return envelope(daily_energy(req), req.limit,
                    """COUNT(*) AS objects,COUNT(actual_kwh) AS valid_energy,SUM(actual_kwh) AS actual_kwh,
                    (SELECT json_agg(x) FROM (SELECT date,SUM(actual_kwh) AS actual_kwh,COUNT(actual_kwh) AS valid_energy FROM data GROUP BY date ORDER BY date) x) AS days""" + extra, "date,id")
