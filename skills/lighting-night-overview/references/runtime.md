# 查询与原型展示契约

load_skill 回包已经包含当前技能的 instructions 和 references，直接读取其中 runtime.md、business.md 和 presentation.schema.json。它们不是用户附件，不调用 read_attached_document；没有附件时不制造 doc_id，不调用无关工具。

## 执行顺序

1. 加载本业务技能和已绑定的 `sql-safe-query`。根据当前对话确认对象、指标、范围、时间、分组和追查意图；使用该技能的案例检索、Schema 核验和只读约束动态生成 SQL。案例查找按技能使用 find/read/grep，不使用 search；无可信案例再用 sql_retrieve_examples。
2. SQL 的唯一执行工具是 `sql_query_readonly`。禁止调用 `query_lighting`，禁止使用固定场景服务替代安全 SQL 技能，不直连数据库，不使用 shell/exec，不执行设备控制。
3. 只要数字或简单文字时直接执行紧凑聚合并回答。需要原型页面时，在本次动态 SQL 中将真实结果组织成下面的 JSON 对象，输出为唯一一行、唯一 `payload` 列，调用 `sql_query_readonly(sql=完整查询,max_rows=1,request_id=本次唯一标识)`。
4. 平台从本次 SQL MCP 的成功回包自动生成六场景 A2UI 和 Workbench。无需也不得另调展示工具重填数值，不输出 A2UI JSON、HTML 或内部表字段。查询失败、截断或契约不完整不能视作正常或零报警。
5. 查询成功后按 `sql-safe-query` 判断是否沉淀案例；交互按钮触发或用户明确只读验收时不写案例。查询和展示不绕过账号的 SQL 服务权限。

## payload（展示元数据可用 SQL 常量，业务数值必须来自本次真实 SELECT）

完整字段、必填项、枚举和嵌套结构以本技能 references/presentation.schema.json 为准，它直接来自平台现有 LightingResult。生成查询前核对该 Schema；不得新增字段、猜字段类型或用近义词替换枚举。列 columns[].type（包括 chart.y）只能是 text、number、time，布尔状态用 text；不能写 integer、numeric、boolean、datetime 等数据库类型。

```json
{
  "schema_version":"lighting-query/v1",
  "scene":"night",
  "status":"partial",
  "query":{
    "id":"本次唯一ASCII短标识","scope":"用户确认的业务范围","timezone":"Asia/Shanghai",
    "window":{"start":"带偏移的真实开始时间","end":"带偏移的真实结束时间"},
    "cutoff":"真实截止时间","generated_at":"数据库当前带偏移时间",
    "basis":"night","report_type":null,
    "source":"授权照明数据查询","coverage":"实际范围与返回覆盖情况",
    "filters":[],"missing":["本次确实缺失的证据"]
  },
  "summary":"本次查询的简短业务结论",
  "metrics":[{"label":"业务指标名称","value":null,"unit":"","note":"缺失原因"}],
  "columns":[{"key":"status","label":"状态","type":"text","unit":""}],
  "rows":[{"id":"真实业务ID","values":{"status":"实际查询值"},"evidence":[],"missing":[],"relationship_verified":false}],
  "row_count":0,"complete":false,"actions":[],"report":[]
}
```

这只是字段说明，不能执行或照抄其中占位符/示例行。实际 SQL 根据安全查询技能检索到的可信 Schema 和当前问题生成；不在程序中预写业务 SQL。可用 PostgreSQL `json_build_object`、`row_to_json`、`json_agg` 组织已查询事实。明细显式 LIMIT，范围总量和指标独立聚合，不能从截断明细外推；不要把所有历史数据和无关关联塞进一条扫描。SQL 本身必须含字面量 `lighting-query/v1`，健康检查和结构核验不加此展示契约。


时间字段必须由 PostgreSQL 带时区类型直接写入 JSON：generated_at 使用 CURRENT_TIMESTAMP，窗口与截止值使用明确的 timestamptz。不要先 AT TIME ZONE 转成无时区时间再用 OF 格式化，也不要用 to_char 生成偏移只有 +00/+08 的时间字符串；这既可能丢失真实偏移，也不符合 RFC 3339。不要由模型手填数据库当前时间。
所有嵌套时间也遵循该规则，包括 rows[].anchor、evidence[].at、evidence_window 和 RTU 能耗窗口。数据库 timestamp without time zone 不能直接写到这些字段，也不能依赖会话默认时区或直接 ::timestamptz 强转。先按安全 SQL 技能核实字段的业务时区：只有可信资料确认后，才能以该已确认时区将原始 timestamp 转成 timestamptz；不能从 query.timezone 反推历史字段时区。无法确认时，选填时间置 null，在对应 missing 中说明“历史时间时区未核实”，保留可确认事实，不开放依赖该时间的追查动作。

若工具回包附带 lighting_presentation_error，代表 SQL 执行结果保留但原型校验失败。读取 errors 中的字段路径和错误类型，对照本技能 Schema 修正动态 SQL后通过 sql_query_readonly 重查；不要声称页面已成功展示，不手填另一份数据，不移除证据来掩盖错误。必要资料不足时明确保留缺口或向用户澄清。

`row_count` 是实际查询范围总量，必须≥返回行数；只有已确认总量等于返回行数时 complete=true。零记录用 empty 且 complete=true；非空但证据不足用 partial。不能为了通过契约编造数字或缺口。未查询到的指标用 null，业务字段只给实际查到的列。

scene 为 night、lamp_alarms、rtu、rtu_alarms、energy、reconcile。energy 必须另带 energy_view=night/week/volatility/saving。night 使用实际照明夜间口径，daily 使用已完成自然日、report_type=D；week/saving严格7天，volatility严格30天。用户问其他范围则按实际问题查询，不能偷偷改成固定窗口；不符合固定视图时直接返回普通查询结果。


证据缺口应按影响范围分别处理。检索资料不充分时先通过 sql_query_readonly 做必要的最小只读 Schema/字段注释核验，不得把“尚未查询”当成“数据库没有证据”。缺历史恢复流水只限制截止时点恢复结论，不阻断已有可信时间口径下的报警发生记录数、受影响对象和清单；history_complete=false、restored_at=null，并明确不能判断历史是否已恢复。查询当前未解除且不按发生时间过滤时，不因选填历史时间未核实而拒绝整个当前状态查询。历史时间筛选确实依赖未知业务时区时，向用户询问时区，不猜测、不把缺口冒充查询成功。

`complete` 仅表示当前 rows 清单是否完整返回，不表示日期覆盖、数据质量、日报完整或聚合是否完成。row_count 按清单同一粒度在 LIMIT 之前计数，不是底层原始记录数；只返回 5 行而范围共有 7 行时，必须 row_count=7、complete=false，即使趋势图含全部7天、指标已汇总全范围。日期覆盖和证据质量写在 coverage/missing 中。校验提示 row coverage is inconsistent 时，核对真实总量与清单长度，修正 complete；不能改掉真实总量、增补假行或丢弃有效证据。

PostgreSQL 明细先在独立 SELECT 中 ORDER BY 并 LIMIT，再由外层 json_agg/jsonb_agg 聚合该子查询；LIMIT 不写进聚合函数的 ORDER BY。rows 是 JSON 属性名，不把未加引号的 rows 用作 SQL 别名。复杂查询按事实聚合、受限明细、JSON 组装分 CTE，优先复用检索中验证过的结构；语法失败时先读 SQL 原始错误并修正对应位置，不用健康检查代替语法修复，也不反复原样执行。

## 原型字段

- 单灯运行：行带 lamp_id；values 按已取得事实提供 lamp_code、pole、road、rtu_code、status、alarms、minutes、actual_kwh、rated_power、previous_kwh、previous_minutes、matched。在线、开灯、故障和巡测覆盖分别表述；能耗首末累计差不足两点、复位或缺测为 null。
- RTU运行：行带 rtu_id；values 可含 rtu_code、name、last_report、status、voltage_a/b/c、current_a/b/c、is_succeeded。evidence 每项给 label/value/unit/at/source/note，失败采样不当有效零值。
- 报警：行带 alarm_id 和查到的 lamp_id/rtu_id；values 可含 alarm_type、triggered_at、last_trigger、recorded_state、recorded_conduct_at、history_complete、restored_at、status_at_cutoff。历史恢复流水未核实则 history_complete=false、restored_at=null，不从末态倒推过去。当前未解除查询按实际当前状态执行，不强行改成历史窗口。
- 能耗：values 可含 date、actual_kwh、previous_kwh、theoretical_kwh、recorded_rate、recorded_saving、source_records。日报仅D，重复日报不擅自选一条。30日上升需同时≥50kWh且≥30%，必须相邻自然日且前日非零。节能率合计有效配对值后算，不平均百分比；没有目标不判断达标。
- 对账：values 可含 date、rtu_code、name、poles、lamps、lamp_kwh、rtu_kwh、lamp_filter_applied、ledger_difference_kwh。当前台账关系未证实历史归属时 relationship_verified=false，不给已验证差额、比值或倒挂结论。

columns 使用上述 key 或查询明确返回的业务别名，label 必须是对用户有意义的业务名称，最多24列。values 值为字符串、数字、布尔或 null，不嵌套对象。

可选 chart 为 {title,x_key,x_label,y:[{key,label,type:"number",unit}],rows:[真实聚合点],filter_key:日期列}。缺日期保留 null，不补零。

可选 report 为 [{title,content}]，所有内容必须来自本次已查结果及明确缺口。单灯九章与 RTU 七章标题、业务规则见 business.md；没有查询依据就不生成假报告。

## 交互与边界

actions 使用唯一 ASCII id，可含 row_id、label、intent；支持 inspect_lamp、inspect_rtu_alarm、inspect_rtu、energy_view、retry 等宿主意图，切换能耗带 energy_view。只为真实存在且具备标识的行提供动作；当前台账未经历史核实不开放跨回路/上下游动作。行的 anchor/evidence_window 只填真实采样锚点和证据窗。

点击动作后宿主从已保存的真实结果解析范围、设备和时间。再次加载安全 SQL 技能，基于这个上下文动态生成新的只读查询；不调用旧固定工具，不把夜间值挪作日报。清单搜索、排序、证据查看和 CSV 复用宿主已有组件，恢复卡片不重放查询。

不执行控制、消警、复电、参数下发、派单；不伪造缺测、阈值、目标、相位映射、单位、保护动作和历史归属。默认不显示 SQL、内部表字段、地址、凭据或调试信息。business.md 中旧 nanobot 的 shell、exec、文件读取和附件能力不等于本平台已配置能力。
