# AI Protocol Platform 全站产品体验改版 · 原型与交互规范（v1）

> 关联 [Issue #141](https://github.com/yuklcool/ai-protocol-platform/issues/141) · 设计基线：v2.1.0 · 日期：2026-10-22  
> **原型阶段，不是已实施的生产页面。所有任务、模型测试、MCP 状态、用户、费用、审计为演示数据，浏览器不会连接平台后端。**

## 1. 打开可交互原型

**[完整原型：full-platform-prototype.html](./full-platform-prototype.html)**（在 GitHub 点击 **Raw** 保存 HTML，再使用浏览器打开）。

这是一个单文件、无第三方 CDN 依赖的全站可交互原型，使用本地模拟状态验证操作逻辑。支持桌面、平板、手机布局。通过左下角「演示视角」在 **普通用户 / 平台管理员** 两套导航中切换。右上角「重置演示」恢复初始状态。

> 如果 GitHub 页面仅显示 HTML 代码，请选择 **Raw / Download raw file**，在本地浏览器打开；仓库并未把此原型部署成生产服务。

## 2. 页面范围（13 个主界面）

| # | 页面 | 主要目的 | 可以在原型中尝试的操作 |
|---|---|---|---|
| 1 | 工作台 | 任务目标优先、最近任务、待确认事项、能力提示 | 输入目标开始任务、快捷示例、恢复任务 |
| 2 | AI 任务工作区 | 会话与动态工作区双栏，计划/执行/成果/资料 | 发演示消息、附加本地文件名、推进模拟步骤、审阅确认、编辑报告、下载演示 TXT |
| 3 | 任务与会话 | 统一任务列表、状态与会话恢复入口 | 按状态/标题/编号筛选，打开任务 |
| 4 | 成果中心 | 从结果返回任务与原始上下文 | 分类筛选、打开成果、恢复原任务 |
| 5 | 能力中心 | 发现公共与个人 Skill | 按归属筛选、启用或停用 |
| 6 | 个人配置 | 用户个人 Skill 与 AI 偏好 | 修改昵称/个人偏好、切换个人 Skill |
| 7 | Root Agent 配置 | 公共能力、模型、测试、状态检查 | 配置绑定、草稿保存、模拟试运行 |
| 8 | 模型接入 | Provider→模型→测试→绑定 | 修改模型字段、模拟能力测试、新建服务弹窗 |
| 9 | MCP 服务 | 连通性、发现、绑定、有效权限 | 修改服务、模拟连通测试、新增服务弹窗 |
| 10 | 知识与资源 | 知识来源、解析和权限 | 添加或删除示例资源 |
| 11 | 用户管理 | 账号与状态管理 | 新增模拟用户、切换启停 |
| 12 | 运行诊断 | 业务步骤 / 详细 Trace 分层 | 展开步骤、查看脱敏示例 |
| 13 | 用量与审计 | 使用指标、审计记录和异常发现 | 查看演示图表、审计记录 |

### 交互贯穿路径

**普通用户：**

```text
工作台输入目标 → 自动建立任务 → 任务对话区
  ├─ 计划：查看业务步骤，不展示模型私有推理
  ├─ 执行：查看步骤摘要与可展开事件
  ├─ 成果：编辑报告草稿 → 保存 → 审核确认 → 下载演示 TXT
  └─ 资料：查看引用与证据占位
      ↓
任务与会话 / 成果中心 → 回到原任务继续
```

**管理员：**

```text
模型接入（参数 / 文本与工具验证）
  ↓
Root Agent 公共模型与能力绑定
  ├─ 公共 Skill / Tool / MCP / Knowledge
  ├─ 与用户个人 Skill / 个人资料严格分开
  └─ 配置草稿 → Agent 试运行
      ↓
运行诊断 / 用量与审计
      ↓
配置版本、Evals、回滚由 Issue #127 承接
```

## 3. 设计语言

- 默认浅色，蓝白和青绿色科技风，保留现有品牌自定义能力。
- 工作台重视输入区与待办，不要求先理解模型、Agent、Skill、MCP 等术语。
- 任务工作区采用桌面「对话 + 内容」双栏，移动端顺序堆叠，不牺牲输入区和可操作性。
- 统一 10~16px 圆角、轻阴影、4px 间距基数，状态同时使用颜色与明确文字。
- 用户级活动与管理员 Trace 分层，避免把技术工具调用流水强行灌给普通用户。
- 动态表单、审批动作和 A2UI 结果沿用现有 v0.9 协议边界，**不能依赖任意 HTML 注入**。

## 4. 设计交互契约（工程落地必须落实）

### Task / Session / Run / Artifact / Surface 的区分

- **Task**：用户可识别的工作目标；是否独立持久化需要后端方案和迁移验证。
- **Session**：持续对话与恢复的上下文，与可信用户 UID 绑定。
- **Run**：一次实际执行过程，真实状态从 AG-UI / ADK 运行事件派生。
- **Artifact**：可持久化的业务产物、附件索引、版本关系；不能把 A2UI 元数据直接当完整文件仓库。
- **A2UI Surface**：客户端的交互表面及状态，不等价于下载文件或已发布报告。

### 展示层的状态

建议用户可理解的状态：`draft`、`running`、`needs_input`、`completed`、`failed`。这仅是**设计语义**；实现时必须定义对真实后端事件的严格映射。无可靠事件时显示「状态未知」，不要根据渲染动画假定任务进展。

### 交互行为及后端需求

| 用户操作 | 原型动作 | 产品正式实现必须满足 |
|---|---|---|
| 新建任务 | 在浏览器内新增模拟任务、自动进入对话 | 后端真实 Session/Run 创建与身份校验 |
| 查看计划 | 展示公开步骤摘要 | 只能展示显式业务计划，不能泄露私有思维链 |
| 下一步 | 模拟进度变化 | 实际状态完全由服务端执行事件驱动，不能直接从前端推动真实步骤 |
| 上传附件 | 只保留文件名称；不上传数据 | 文件入库、解析状态、UID 授权、大小和格式约束 |
| 用户确认 | 修改模拟任务状态 | A2UI 受控 action、可审计权限、必要的幂等和防重放 |
| 保存草稿 | 仅存当前演示内存 | Artifact 草稿版本与 ACL、失败反馈 |
| 导出 TXT | 下载示例文本 | 真正的服务端文件生成、授权下载；PDF/DOCX 按能力建设，不制作假按钮 |
| 模型/MCP 测试 | 模拟成功标识 | 实际 Provider/MCP 请求，保留诊断证据，区分“已保存”和“可调用” |
| 修改用户角色 | 改变浏览器演示列表 | 服务端校验用户身份、角色、资源权限和审计 |

## 5. 现有代码映射

| 原型区域 | 优先复用或调整 |
|---|---|
| Shell 与导航 | `frontend/src/components/navigation/ConsoleSidebar.tsx`、`ConsoleFrame.tsx` |
| 工作台 | `frontend/src/app/workspace/page.tsx` |
| 任务双栏与消息 | `frontend/src/components/chat/ChatShell.tsx`、`Workbench.tsx`、`ChatMessageList.tsx` |
| 执行过程 | `frontend/src/components/chat/ActivityPanel.tsx`、`frontend/src/components/activity/` |
| 动态 UI | `frontend/src/providers/SurfaceRegistry*`、`frontend/src/components/protocols/A2UISurfaceMount*` |
| 历史与成果 | `frontend/src/app/sessions/page.tsx`、`frontend/src/app/results/page.tsx` |
| Agent | `frontend/src/components/agent/RootAgentSettingsPage.tsx` |
| 模型 | `frontend/src/app/admin/model-providers/page.tsx` |
| 后台 | `frontend/src/app/admin/page.tsx`、相关 MCP、用户、分析与审计页面 |
| Runtime | `backend/adk/agui.py` 和现有 `/api/agent/stream`；不修改 Google ADK 引擎源码 |

## 6. 交付与验收建议

- **P0-A**：将此原型拆解为新 IA、可复用组件、真实页面和用户任务路径，完成交互签收。
- **P0-B**：对话主工作区、计划和进度、失败与恢复、审批与结果审阅真实接入。
- **P1**：任务 / Session / Run / Artifact 关联、服务端搜索、成果预览与下载。
- **P1/P2**：Agent 配置与模型/MCP 接入流程统一；关联 #127 配置版本/Evals/Trace，#129 通用 A2UI Rendering Skill。

每个阶段需覆盖 1440/768/390 三种尺寸、关键态（空/加载/错/权限拒绝/中断）、键盘操作、会话重载、真实模型与工具调用、A2UI 动作以及 UID/ACL 拒绝测试。

## 7. 安全与项目边界

1. 不引入另一套 Agent Runtime；继续 Google ADK + Single Root Agent。
2. 不恢复已删除的租户、权限组、Skill-as-Agent 旧架构。
3. 不修改 Google ADK 内核源代码，优先组合现有 AG-UI / A2UI / MCP Apps。
4. MCP Apps 保持独立浏览器 Origin 和通信隔离。
5. 原型无凭证输入或外部 API 请求；生产密钥交由安全存储管理。
6. 此原型文件是**设计评审资产**，不是生产前端源码，也不证明后端已具备演示中描绘的新能力。

相关：[全站视觉基础 #122](https://github.com/yuklcool/ai-protocol-platform/issues/122) · [体验主线 #141](https://github.com/yuklcool/ai-protocol-platform/issues/141) · [版本/评估/回放 #127](https://github.com/yuklcool/ai-protocol-platform/issues/127) · [通用 A2UI Skill #129](https://github.com/yuklcool/ai-protocol-platform/issues/129)。
