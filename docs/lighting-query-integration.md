# 照明 A2UI 集成

用户对话 → `load_skill(sql-safe-query)` 与照明业务技能 → 已验证案例/静态样例检索 → 根据当前问题动态生成只读 SQL → `sql_query_readonly` → 已注册结果转换 → AG-UI `A2UI_SURFACE` → 原型 Workbench。

`query_lighting` 固定查询服务已移除。程序不维护夜间、报警或能耗的固定业务 SQL。展示转换不执行 SQL，也不接收模型另填的查询结果。SQL 的权限与执行边界继续由现有安全查询技能和 SQL MCP 管理。

只要数字或简单结论时，普通 SQL 直接返回结果。需要原型时，动态 SQL 返回唯一一行 payload，符合 backend/lighting/results.py 的 lighting-query/v1；完整编写规则见各业务技能 references/runtime.md。业务数值来自本次真实查询，展示元数据可用 SQL 常量。失败、截断、畸形返回不能当正常；缺失证据保持未知。

六场景共用宿主视图、查询范围、指标、清单、趋势、证据抽屉、报告和 CSV。CSV 只导出当前过滤的已返回清单。动作只提交 actionId，服务器从本会话保存的真实结果解析设备、范围和窗口，再由安全 SQL 技能动态查询；执行限于原 SQL 数据源。历史归属未证实时，不开放跨层级按钮。恢复卡片不重放查询。

部署和验证参见 infrastructure/lighting-skills/README.md。更新技能路由后，停用旧固定查询 MCP 和容器，保留现有 SQL、安全查询检索和 OpenViking 服务。所有测试在 GitHub 执行；生产接通和原型完全验收需要真实运行证据，不能以合成数据代替，也不自动关闭 #152。
