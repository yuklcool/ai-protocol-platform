# #141 第三批：聊天内的公开业务计划

本批基于 #143 的消息流实现，合并顺序为 #143 → 本批；#144 的服务端搜索没有依赖。无需新建 Runtime、Task 表或流式端点。不关闭整个 Epic。

## 用户与配置路径

管理员在 Root Agent 设置的“工具”中显式绑定 **任务计划与进度**（`update_task_plan`）。系统不会自动修改已保存的 Root 配置。绑定后，多步骤任务的指令要求助手先报告公开步骤，再随实际工作更新同一计划；简单回答不必创建计划。每次工具调用沿用现有 Root 绑定与 deniedTools 检查，撤销后立即拒绝。它与“允许模型直接生成 A2UI”相互独立：计划由服务端固定映射生成，并非模型手写 A2UI。

用户在消息流内看到任务标题、按顺序排列的步骤、明确状态与阻塞原因。没有步骤时不生成空卡；参数错误返回可识别错误给 Agent 修正，不提交不完整状态。没有公开计划仍显示已有的真实执行活动，不根据工具名、工具返回或 Run 结束推断业务步骤完成。

计划使用 v0.9 Basic Catalog 的 Column/Card/Text，由共享结果映射和回调发出 `A2UI_SURFACE`，没有专属 React 渲染器、任意 HTML/JS 或新的前端任务引擎。`displayOnly` 是通用的信息展示元数据：不订阅可执行操作、不显示“已提交”徽标；恢复历史后保留原来的标题与状态。需要确认时仍使用现有确认表单及授权 Action。

## 数据与接口契约

| 对象 | 本批含义 |
| --- | --- |
| Session | 身份与资源 ACL 保护的现有 ADK 会话，计划只属于该 Session |
| Plan | 助手明确报告的公开计划快照，不是调度器或独立持久 Task |
| Run | 既有 AG-UI 运行；结束不会自动改变 Plan 的状态 |
| Surface | Plan 的标准 A2UI 展示，稳定 ID 为 `task_plan:{plan_id}` |

新增原生工具参数：`title`、完整 `steps`、可选 `plan_id`、`expected_revision`。每步包含唯一稳定 `id`、`title`、`status`、可选 `detail`；状态为 `pending/running/completed/failed/cancelled/needs_input`。失败与待补充必须附公开原因。不接受额外步骤字段。标题最多 160 字、详情最多 600 字、每计划 1–20 步、每 Session 最多 25 个计划；达到限制仍允许更新已有计划。

创建时省略 ID、revision 为 0，ID 由后端随机生成；更新必须引用同一 Session 中存在的 ID 并提交上一版 revision。错误包括 `session_required/invalid_plan/invalid_plan_id/plan_not_found/revision_conflict/session_plan_limit`。过期更新返回当前 revision，不覆盖；相同内容的重复更新返回原快照，不增加版本或时间。

```json
{
  "title": "检查资料",
  "steps": [
    {"id": "read", "title": "读取资料", "status": "running"},
    {"id": "check", "title": "核对数据", "status": "pending"}
  ]
}
```

返回 `{"task_plan": {"plan_id": "后端生成的32位ID", "revision": 1, "title": "...", "steps": [], "reported_at": "UTC时间"}}`（此处步骤省略）。后续提交相同 plan_id、expected_revision=1 和完整的新步骤。

快照写入 Session 域的 `task_plan:*`；共享回调将最新 A2UI 写入现有 `a2ui_surface:*`。不用 `app:`、`user:` 或浏览器本地状态。刷新使用已授权 `/messages` 恢复，不调用模型。共享回调现在保留首次合法 `createdAt`，新内容覆盖旧内容而卡片位置不移动；坏旧时间戳可被新渲染修复。

revision 是当前 Session 状态内的顺序更新检查，**不是数据库级并发 CAS 或副作用幂等账本**。不承诺多个并行 Run 写同一计划时的强一致性，不新增并行执行入口。report 时间仅表示后端收到报告的时间，不冒充实际业务开始/结束时间。计划无独立 Run 关联或跨会话索引，后续统一任务索引仍需独立数据模型。

## 中断与恢复

停止、失败、断网只影响原有运行流，计划保留最近报告，卡片明确说明该状态来自助手最近报告。不会自动把“执行中”变成“成功”，也不会声称后台持续执行。用户在对话中提出继续请求后才开启新的正常 Run；计划不提供自动重试或重放业务动作的按钮。未提供计划审批、文件导出或自动恢复功能。

## 验证与回滚

单测使用真实 ADK FunctionTool declaration、JSON 参数、ADK State，以及生产回调/LatencyTracker，验证规范 v0.9 输出、状态校验、顺序冲突、重复提交、数量限制、共享域隔离、权限撤销、首次时间戳和坏状态恢复。前端驱动真实 A2UI SDK，验证通用信息卡无 Action、原位更新和恢复标题。

`task-plan-live.spec.js` 使用生产前端、真实 JWT、PostgreSQL Session、真实 ADK 工具执行/回调与 HTTP 确定性模型，验证创建→更新→刷新，以及 1440/768/390。没有替换前端 SSE 或 A2UI 事件；**仍不是外部真实 Provider 的规划行为验收**。各提交结果以 PR 中的实际 CI 与截图为准。

回滚：撤销 Root 工具绑定即可阻止新报告；撤回本批代码无需数据库结构迁移。已保存的标准 A2UI 快照继续能按现有协议恢复，旧版客户端不会识别 displayOnly 的纯展示语义，但卡片本身没有按钮。保留所有原路由、会话和授权端点。
