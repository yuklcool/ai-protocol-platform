# 迁移后的业务核查参考

本文件保留源技能的业务核查规则；平台工具、默认交付和历史证据约束以当前 SKILL.md、runtime.md 为准。示例不是实时业务事实。

## 来源：rtu-lamp-energy-inversion-query

# RTU/单灯能耗倒挂查询

## 目标

找出指定日期或日期范围内：

> RTU 下挂载单灯能耗合计 > RTU 上报能耗

的 RTU 清单，并按“超出 kWh”倒序输出。

## 必须遵循

- 统一遵循全局 `sql-safe-query` 规范：先确认目标与真实 schema，SQL 只走 `sql_query_readonly`。
- 不要凭经验改关联链路；如果字段或表报错，回退到 `sql-safe-query` 标准确认流程。
- 默认查询昨日：`CURRENT_DATE - INTERVAL '1 day'`。
- 默认只查日报：`report_type = 'D'`。
- RTU 能耗过滤：`r_energy_report.all_electric_energy >= 0 AND < 1500`。
- 单灯能耗过滤：`l_energy_report.all_electric_energy >= 0 AND < 100`。
- 结果优先返回汇总，不默认展开全部单灯明细。
- 默认不在回复正文输出 SQL；只有用户明确要求“附 SQL / 展示 SQL / 给我查询语句”时，才提供可追溯 SQL。

## 固定关联链路

用于判断“RTU 下挂载单灯”的标准链路：

```text
sl.l_energy_report.alone_lamp_id
→ sl.l_alonelamp.alone_lamp_id
→ sl.l_alonelamp.rtu_road_id
→ sl.r_rturoad.rturoad_id
→ sl.r_rturoad.road_switch_id
→ sl.r_road_switch.road_switch_id
→ sl.r_road_switch.control_cabinet_id
→ sl.r_rtu.control_cabinet_id
```

不要改用 `l_lamppost.transformer_id → r_rtu.control_cabinet_id` 作为主链路；该链路可能把大量单灯错误归并到同一 RTU，适合做交叉校验，不适合作为本技能默认口径。

## 标准输出字段

按以下字段输出：

| 字段 | 说明 |
|---|---|
| 日期 | 日报日期 |
| RTU编号 | `r_rtu.rtu_code` |
| RTU名称 | `r_rtu.rtu_name` |
| 有单灯能耗灯杆数 | 当日有单灯能耗日报的灯杆数 |
| 有单灯能耗灯源数 | 当日有单灯能耗日报的灯源数 |
| 下挂单灯能耗合计kWh | 单灯日报能耗汇总 |
| RTU上报能耗kWh | RTU 日报能耗汇总 |
| 超出kWh | 单灯合计 - RTU 上报 |
| 单灯/RTU比值 | 单灯合计 / RTU 上报 |

## 固定查询逻辑

默认查询昨日 D 日报。执行时按 `sql-safe-query` 标准确认流程生成并执行只读 SQL，不在回复正文默认展示 SQL。

查询逻辑：

1. 先确定目标日期或日期范围：
   - 用户未指定时，默认昨日。
   - 用户指定单日时按该自然日。
   - 用户指定范围时按自然日逐日聚合。
2. 聚合 RTU 日报能耗：
   - 来源：`sl.r_energy_report`。
   - 口径：`report_type='D'`。
   - 过滤：`all_electric_energy IS NOT NULL AND all_electric_energy >= 0 AND all_electric_energy < 1500`。
   - 粒度：`rtu_id + report_date`。
3. 聚合 RTU 下挂单灯日报能耗：
   - 来源：`sl.l_energy_report`。
   - 关联链路：`l_energy_report -> l_alonelamp -> r_rturoad -> r_road_switch -> r_rtu`。
   - 口径：`report_type='D'`。
   - 过滤：`all_electric_energy IS NOT NULL AND all_electric_energy >= 0 AND all_electric_energy < 100`。
   - 粒度：`rtu_id + report_date`。
4. 对比筛选倒挂：
   - 条件：`下挂单灯能耗合计 > RTU 上报能耗`。
   - 输出字段：日期、RTU编号、RTU名称、有单灯能耗灯杆数、有单灯能耗灯源数、下挂单灯能耗合计kWh、RTU上报能耗kWh、超出kWh、单灯/RTU比值。
   - 默认按超出 kWh 降序返回 Top 50。
5. 常用过滤：
   - 指定 RTU 编号或名称时，在最终异常结果中按 RTU 过滤。
   - 用户要求“只看明显异常”时，可增加比值阈值，例如单灯/RTU 比值 >= 1.2。

如用户明确要求“附 SQL / 展示 SQL / 给我查询语句”，再按上述固定逻辑提供本次实际执行 SQL。

## 结果解释

- 比值轻微高于 1：优先看抄表时间差、过滤阈值、是否存在 RTU 分相/支路统计差异。
- 比值显著高于 1：优先核查挂载关系、回路/控制箱/RTU 台账映射、单灯能耗累计异常。
- 单个 RTU 挂载灯源数远超常规：优先判断为台账映射异常，不要直接判定现场能耗真实异常。
- 如需定位原因，再按 RTU 展开：回路分组、道路分组、单灯能耗 TopN、灯杆台账数量与 r_rturoad 灯数对比。

## 交付格式

默认简洁返回：

1. 查询日期/范围与口径
2. 异常 RTU 汇总表
3. 关键结论：重点 RTU、最大超出值、最大比值
4. 说明：关联链路、过滤阈值、是否需要继续展开明细
