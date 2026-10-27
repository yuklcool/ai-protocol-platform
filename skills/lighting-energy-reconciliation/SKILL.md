---
name: lighting-energy-reconciliation
description: 查询单灯合计与RTU D日报的能耗对账、疑似倒挂、挂载关系及有效数据覆盖。用户问“单灯合计为何高于RTU”“哪些RTU倒挂”“单灯RTU能耗对不上”时使用，默认昨日自然日。
---

# 单灯 / RTU 能耗对账

1. 加载 `sql-safe-query`，结合当前对话的日期、RTU 和对账指标检索可信案例、动态生成 SQL，只通过 `sql_query_readonly` 执行。默认昨日完整自然日，逐日D日报；原型 payload 的 scene=reconcile。
2. 固定主链路：单灯日报→单灯→`r_rturoad`→`r_road_switch`→控制箱→RTU，不能使用灯杆变压器关系替代。单灯逐条0≤kWh<100、RTU0≤kWh<1500；重复日报、歧义关系不重复累计。
3. 页面给出日期、RTU、有效灯杆/灯源、单灯合计、RTU日报、当前台账映射差额及历史证据状态。未取得历史变更记录时，当前台账映射差额只作核查线索，已验证差额/比值为空，不直接认定历史倒挂。
4. RTU有效日报为0与缺日报/无效日报分别说明。有效零分母不算比值；缺失不补零；数据不足不称全网正常。清单截断不当作全范围统计。
5. 用户追查时明确所需日期、RTU、回路和抄表时刻。没有实测分项不按比例构造回路或单灯能耗；无历史归属证据不扩展影响范围。

详见 `references/business.md` 和 `references/runtime.md`。
