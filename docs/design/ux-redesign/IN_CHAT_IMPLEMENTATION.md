# #141 第一批实现：消息流内的执行与交互

本切片以 #141 在 2026-10-22 修正的“对话消息流优先”为准，复用 v2.1.0 的真实产品链路。设计参考 PR #142；本提交不合并设计分支，也不关闭整个 Epic。

## 已实现的用户路径

登录 → `/chat/root-agent` 输入任务 → 同一消息流查看真实执行活动 → A2UI 输入/确认 → 授权 Action 驱动同一 Agent 继续 → 读取结果。普通文字问答不强制生成任务卡；`/workspace` 作为辅助概览保留。旧会话和书签路径继续有效。

Root 对话默认折叠辅助工作区，用户可显式展开，也可点击成果卡“查看预览”。已有明确存储的折叠偏好仍生效。交互表单使用现有 `placement:chat`；管理员显式配置为工作区的其他 Surface 保持其位置。

## 数据模型与真实能力边界

| 对象 | 数据来源与作用 | 恢复规则 |
| --- | --- | --- |
| Session | 现有服务端会话，标识用户对话与附件 | 认证 `/messages`、`/activity` 及持久化 A2UI 状态 |
| Run | 同一 HttpAgent 的 `RUN_STARTED.runId` 与终止事件 | 当前切片不新增后台 Run 表；历史工具存在不证明整个 Run 成功 |
| 执行活动 | 实际 `TOOL_CALL_START` / `TOOL_CALL_RESULT`、服务端阶段标签 | `/activity` 的调用按持久消息时间归位，标记“历史活动记录” |
| 业务计划 | 需要 Agent 显式生成的公开步骤或确定性业务编译 | 本切片不从工具调用推测计划，不生成虚假步骤或百分比；结构化计划后续增量实施 |
| A2UI Surface | 现有 v0.9 SDK / SurfaceRegistry，表单与可复用 UI | 沿用已有确认卡重放策略及普通 A2UI 复用策略 |
| 成果卡 | 已存在、可访问 Surface 的标题和说明元数据 | 与历史消息时间交错，不将摘要伪装为文件；无下载或导出能力时不显示按钮 |

## 事件契约

`useChatExecution` 观察生产的同一 HttpAgent，普通聊天与 A2UI action-run 均进入同一消息流；不建立第二个 Runtime 或 SSE 请求。

- `RUN_STARTED`：使用真实 `runId` 建立稳定卡片标识，并记录当前消息锚点。
- `STAGE_PROGRESS`：只展示服务端公开标签；不读取或展示私有推理。
- `TOOL_CALL_START`：新增或更新真实调用 ID。
- `TOOL_CALL_END`：只是参数流结束，不当成工具完成。
- `TOOL_CALL_RESULT`：说明已收到返回，UI 不据此宣称业务成功。
- `RUN_FINISHED` / `RUN_ERROR`：标记运行结束或失败，不把整次业务目标判为成功。
- 非正常流终止：标记中断；显式停止保留“已请求停止”，不宣称服务器撤销已执行动作。

不自动重放工具、重新发送确认或以浏览器状态伪装后台持续执行。身份或会话改变时，旧订阅与晚到的活动响应不能污染新会话。

## A2UI 操作与恢复

仍使用原有 `useActionDrivenAgent`、`A2UISurfaceMount` 和后端 UID / Owner / ACL / Root policy 校验。单次确认卡在成功后由同步 guard 阻止再次 dispatch，并通过原生 disabled fieldset 禁用键盘与鼠标；重放的只读卡也不能触发 `run:` 操作。普通可复用 A2UI 不因一次操作而永久锁住。

前端防重复不等于服务器 at-most-once：不可逆业务动作仍需要其服务端幂等与确认策略。跨标签页重放、网络不明结果的安全重试等，继续作为 Epic 的后续端到端验收项，不在本切片冒充已完成。

## 实现与回滚

- `ChatMessageList`：稳定位置的执行卡、A2UI 与成果卡；修复历史消息和 Surface 不能按原始时间交错的问题。
- `useChatExecution`：生产共享流的只读活动投影。
- `useSessionActivity`：按 UID / Session 清空旧状态，取消失效请求，显式显示历史读取失败。
- `ChatPlacementForm` / `A2UISurfaceMount`：确认、忙碌、停止、已处理及键盘防重保护。
- `HomeGate` / 导航：默认对话入口，保留概览和原有其他路由。

未修改 ADK 引擎、数据库 Schema、授权接口或 MCP Apps 独立源。代码回滚可撤回本切片的前端与文档提交，无数据迁移；回滚会恢复旧入口及展示行为。

## 验证层次

单测覆盖 Run/工具终止区别、截断/失败/停止、用户切换与晚响应、卡片位置稳定、历史归位、只读/已处理表单防重复及普通聊天。既有真实 Provider 浏览器脚本新增聊天内表单、原位活动和 1440/768/390 视口断言；脚本纳入不代表外部真实 Provider 已实跑。

本地浏览器协议 fixture 验证生产前端的渲染和 AG-UI/A2UI 往返，与真实 Provider、持久化 PostgreSQL、MCP Apps 联调分别记录。完整 Epic 仍需后续业务计划、统一任务/成果索引、配置引导及专门安全恢复验收；#127 的版本/Evals、#129 的通用 Rendering Skill 与 #124 的沙箱减容维持独立范围。
