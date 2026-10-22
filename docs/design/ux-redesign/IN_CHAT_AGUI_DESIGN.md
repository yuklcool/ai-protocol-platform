# Issue #141 · 对话内 AG-UI × A2UI 交互改版（修正后的 P0 主目标）

> 需求确认（2026-10-22）：**用户想在聊天消息区域直接看到并操作 Agent 产生的交互界面**。  
> 不是工作台多一个输入框；不是在聊天之外另建「任务管理系统」；更不是把 AG-UI 工具调用 JSON 当文本显示。

## 0. 原实施方向的偏差与处置

之前尝试的 `feat/issue-141-workspace-task-entry` 仅实现「工作台目标 → Root 对话预填草稿」，**不能解决对话内交互需求**。该分支尚未创建 PR、尚未合并：不得作为 Issue #141 的 P0 核心验收；不应在未重设优先级之前合并。它可作为低优先级的可选导航便捷优化，由后续单独评估。

**P0 的唯一首要目标**：用户待在同一会话的消息流内，即可完成规划、观察真实进度、点击确认/修改、查看动态结果并驱动 Agent 下一轮执行。复杂文件预览/长表格可在可折叠右侧工作区扩展，但不把它作为完成交互的必经路径。

## 1. 目标界面与验收流程

```text
[用户] 分析这两份资料，列出风险并给建议。

[AI · 对话内「任务计划卡片」]
  分析计划                          0 / 3
  ○ 解析资料与确认范围
  ○ 提取证据并分析风险
  ○ 形成总结报告
  [开始执行] [调整要求]

[AI · 同一位置的卡片实时更新]
  ✓ 资料已解析
  ◉ 正在分析风险...
  ○ 等待报告生成
  [展开步骤 / 来源 / 工具调用]

[AI · 在消息流中插入「需要确认」表单]
  发现 3 项关键风险。是否继续输出完整报告？
  输出类型： [详细报告 ▼]
  是否包含优化建议： [✓]
  [确认继续] [修改要求] [取消]

[用户点击确认] → A2UI Action（经过服务端授权）→ Agent 继续执行

[AI · 对话内「成果卡片」]
  风险分析报告已完成。
  [预览] [调整结论] [保存 / 下载（后端真实支持后才显示）]
```

上述示意不是固定业务流程模板：Root Agent 在普通问题时可继续直接返回文本，只有复杂任务/可视化/需要人工操作时生成结构化交互。

## 2. 协议与责任边界

| 层次 | 负责什么 | 当前项目复用 |
|---|---|---|
| Google ADK + Root Agent | 理解用户请求、规划、调用授权 Skill/Tool/MCP、产出结果 | `backend/agents/root_runtime.py` 及现有运行时 |
| **AG-UI** | 发送 Run、Text、Tool、State 和 Custom 事件，驱动同一会话的状态更新 | `backend/adk/agui.py`、`frontend/src/providers/AGUIProvider.tsx` |
| **A2UI v0.9** | 定义卡片、表单、按钮、布局和可交互的 Surface 内容 | `backend/adk/a2ui.py`、现有 SDK Basic Catalog |
| React 对话渲染 | 在**聊天消息流内**把文本、任务卡、表单、结果卡按顺序展示并原位更新 | `ChatMessageList.tsx`、`MessageBubble.tsx`、`ChatPlacementForm.tsx` |
| Action 往返 | 用户点击/提交 → 服务端授权持久化/触发 Agent → 更新流事件回到同一会话 | `A2UISurfaceMount.tsx`、`useActionDrivenAgent.ts`、`surface-action-run` |

**AG-UI 不是组件库**：它提供 Agent 与前端传递状态和事件的通信方式；实际可操作界面使用 A2UI 的受控组件（或由 React 基于可信的结构化运行状态渲染）。不需要建立第二套 Agent Runtime，也不允许由 LLM 输出任意 HTML/JavaScript 直接执行。

## 3. 源码已存在的能力（不要重复建设）

- `MessageBubble.tsx` 已支持 `send_a2ui_json_to_client` 的工具结果，对 `surface_id=chat` 或缺省的结果直接使用 `A2UIRenderer` **内联渲染**。
- `SurfaceRegistry` 已支持 `artifact.placement === "chat"`。 `ChatMessageList.tsx` 按消息流插入 `ChatPlacementForm`；已有真实测试 `ChatMessageList.forms.test.tsx`。
- `ChatPlacementForm` 内的 `A2UISurfaceMount(triggerOnAction)` 已支持点击后运行 `surface-action-run`，并提供运行中/失败反馈。
- `A2UISurfaceMount` 对 `chat:send`、`run:`、普通持久化 Action 有不同路由。
- `useActionDrivenAgent.ts` 已使用 AG-UI SSE 处理消息、工具、阶段等运行事件。
- `ChatShell.tsx` 中的 `ActivityPanel` 主要作为工作区面板，而**不是**面向普通用户的消息流级步骤卡；这是本轮重点差距。

## 4. 第一阶段必做的设计与代码范围

### A. 对话内通用任务计划/进度组件（P0）

- 设计统一的 `ChatTaskTimeline` / `ChatExecutionCard`，**作为对话列表一项**，而不是仅显示在右侧 Activity Tab。
- 展示明确的计划摘要与真实执行步骤、步骤状态（`pending`/`running`/`needs_input`/`completed`/`failed`）和可展开证据。计划必须由 Agent 显式输出或后端确定性编译，**不得由任意 Tool Call 猜测为计划**，不展示模型私有推理链。
- 在同一个 Run/任务消息位置原位更新卡片；收到工具进度事件时可更新详细说明。用服务端可用的 Run/Message/Surface 标识稳定锚定，避免刷新、流式文本到达时卡片跳跃和重复显示。
- 若后端没有可靠的结构化计划事件，先采用**只读真实活动时间线**，明确标记「执行活动」而非「计划」；待增量约定 Custom Event/State 后启用计划/阶段模型。

### B. 对话内受控交互卡片（P0）

- 优先复用现有 A2UI v0.9 `placement:chat` + `A2UISurfaceMount`，覆盖选择、文本输入、确认、取消、修改、结果预览。
- 按 SDK Basic Catalog 实际组件能力设计，复杂输入可走受控弹出式表单，但入口/反馈仍在对话流中。
- 操作提交时：按钮置忙 → 后端 UID/ACL/Root policy 验证 → action id/状态冲突校验 → AG-UI 回传下一轮内容 → 成功/失败在原卡片反馈。不可逆动作必须有明确确认与去重处理。
- 当前会话已有已处理的交互卡不应在恢复时变成可重复执行的「活按钮」；新回合或复用场景按实际策略重新生成新状态。

### C. 对话内成果卡（P0/P1）

- 任务结束后在对话中出现结果摘要卡，支持后续追问/再执行。长文/文档可以点击展开右侧 Workbench，**右栏是辅助预览而非主交互入口**。
- 文件按钮与实际 Artifact 存储、下载接口绑定；不能把 Surface 摘要或静态演示的“下载”当成真实可下载文件。
- 普通文本回答不强制生成卡片。

### D. 后端事件与页面状态映射（P0）

- 尽量使用现有 `RUN_STARTED/RUN_FINISHED/RUN_ERROR`、`TEXT_MESSAGE_*`、`TOOL_CALL_*`、`STATE_*`、`CUSTOM`、`A2UI_SURFACE`；需要“计划/步骤”时**在应用层新增明确的结构化状态或 CUSTOM 事件**，不修改 Google ADK 内核。
- 为计划和步骤定义最小可解析的数据契约（`runId`, `stepId`, `status`, `label`, `updatedAt`，可选 `messageId`/`surfaceId`）。事件必须与实际 Run 生命周期一致；没有真实步骤时不生成假进度或假百分比。
- 所有恢复以服务端授权的会话/活动/A2UI Surface 状态为准；切换 UID/会话时清理旧 UI、旧操作句柄与草稿。

## 5. 建议修改的现有代码

| 优先级 | 文件 | 修改意图 |
|---|---|---|
| P0 | `frontend/src/components/chat/ChatMessageList.tsx` | 在同一个消息流插入任务状态卡、交互卡和结果卡，遵循可靠锚定 |
| P0 | `frontend/src/components/chat/MessageBubble.tsx` | 保留 inline A2UI 路由，扩展统一卡片呈现，避免 Raw JSON |
| P0 | `frontend/src/components/chat/ChatPlacementForm.tsx` | 通用 `placement:chat`，不只围绕已有 obligation 案例 |
| P0 | `frontend/src/components/protocols/A2UISurfaceMount.tsx` | 完善加载/完成/失败/重复点击保护、动作授权反馈 |
| P0 | `frontend/src/hooks/useActionDrivenAgent.ts` | action-run 的 AG-UI 进度/文本/工具事件统一到当前聊天上下文 |
| P0 | `frontend/src/components/chat/ChatShell.tsx` | 将用户可见计划/步骤状态传递给消息流；保持历史会话恢复 |
| P0/P1 | 现有 `AGUIProvider`/后端 `agui.py` | 增量事件模型、Run 与步骤 ID，对外保持现有协议 |
| P1 | `ActivityPanel.tsx` / `Workbench.tsx` | 原 Activity 面板成为“详情/高级诊断”，不再是查看基本进度必经入口 |

## 6. 必须验证的端到端场景

- [ ] 新开对话：用户直接输入目标，Root Agent 生成文本 + 真实计划卡；卡片在聊天消息流可见。
- [ ] 运行阶段：进度在**原卡片更新**，而不是不断插入重复 JSON 或只在右栏显示。
- [ ] 交互阶段：用户在聊天中选项/输入/确认 → 真实 `surface-action-run` / AG-UI 通路 → Agent 继续回答并更新卡片。
- [ ] 取消、失败、网络断开、重连、重试：原对话中有可信反馈，不自动重放不可逆动作。
- [ ] 刷新、恢复旧会话、不同用户切换：卡片、已确认状态与消息次序正确，不重复执行。
- [ ] 手机端：无需打开独立工作区，也能查看与操作完整任务。
- [ ] 权限：A2UI 交互走实时有效 UID/ACL/Root policy；MCP Apps 继续使用独立浏览器 Origin 与受控通信。
- [ ] 普通纯聊天：不强制创建任务、卡片或人工计划。
- [ ] 测试至少包含前端消息列表交互、A2UI v0.9 action、后端会话 ACL、真实 AG-UI 流式回归与手动浏览器验收。

## 7. 与现有 Issue 的关系

- #141：**主体验 Epic，优先完成对话内 AG-UI × A2UI**；其他导航/工作台/管理员体验随后整合。
- #129：平台通用 A2UI Rendering Skill，负责告诉 Root Agent 何时、如何生成 v0.9 UI；不在 #141 中复制协议实现。
- #127：配置版本/Evals/Trace Replay 与治理功能，不能把其管理端工作当成用户对话交互的 P0 依赖。
- #122 / PR #137：浅色设计系统复用，不再大面积重写视觉框架。

> **验收关键句：用户不离开聊天消息流，即可看到任务计划、实时执行、可点击的交互组件，并由操作驱动 Agent 继续执行直到得到结果。**
