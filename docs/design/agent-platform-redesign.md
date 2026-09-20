# AI Protocol Platform — 产品重设计方案

> 状态：Proposal  
> Target：v1.1 — Platform Productization  
> Parent Epic：#74  
> 日期：2026-09-20

![Agent Platform Redesign](./agent-platform-redesign.svg)

## 1. 重设计目标

当前平台已经具备 Model Provider、Skill、Native Tools、MCP/MCP Apps、AG-UI、A2UI、Tenant、Tool Permission、Session/Memory 等底层能力，但产品层仍以历史 Skill Studio / Admin 页面为中心组织，导致用户必须理解内部数据结构才能完成 Agent 配置。

本方案不继续在旧页面上叠加字段，而是把产品重新定义为三层：

```text
Agents
负责：创建、配置、测试、发布真正面向用户的 Agent

Resources
负责：给 Agent 提供能力
Skills / Tools / MCP / Models / Knowledge / Secrets

Administration
负责：治理
Tenant / User / Group / Permission / Usage / Audit
```

Developer 能力单独收口，用于 Playground、A2UI、MCP Apps、协议调试和 Demo，不再污染主用户路径。

## 2. 产品模型

底层第一阶段继续复用现有：

```text
SkillConfig
   ↓
Agent Factory
   ↓
Google ADK Agent
```

产品层新增“暴露方式”语义，将同一 SkillConfig 明确区分为：

- `user-facing`：真正出现在 Agents / Chat 的 Agent
- `internal`：可复用 Skill / Tool-like capability
- `system`：平台内部 Agent，例如 authoring assistant
- `development`：Demo / Workshop / Experimental

主聊天切换器只展示 `user-facing`，不再把 Web Researcher、Maps、Workspace Demo 等内部能力当作 Agent。

## 3. 一级信息架构

```text
Overview

Agents
  My Agents

Resources
  Skills
  Tools
  MCP Servers
  Models
  Knowledge
  Secrets

Administration
  Tenants
  Users & Groups
  Permissions
  Usage
  Audit

Developer
  Playground
  A2UI
  MCP Apps
  Protocol Inspector

Settings
```

角色权限决定是否显示 Administration / Developer。

## 4. 核心用户路径

### 4.1 创建 Agent

```text
Create Agent
  ↓
Basic
  ↓
Model
  ↓
Capabilities
  ├ Skills
  ├ Tools
  └ MCP
  ↓
Create
  ↓
Agent Studio
```

创建流程只保留最低必要配置，复杂参数进入 Studio 后再补充。

### 4.2 配置 Agent

```text
Agent Studio

Overview
Model
Prompt
Capabilities
  Skills
  Tools
  MCP
Knowledge
Interaction
Permissions
Advanced
```

右侧固定 Test / Preview，形成“配置即测试”的闭环。

### 4.3 使用 Agent

Chat 页面只负责：
- 切换 user-facing Agent
- 新建 / 恢复会话
- 对话
- A2UI / MCP Apps 交互

不再承担 Agent 配置和平台管理职责。

## 5. Agent Studio

采用三栏布局：

```text
┌──────────────┬──────────────────────────────┬──────────────────────┐
│ 配置导航      │ 当前配置                     │ Test / Preview       │
│              │                              │                      │
│ Overview     │                              │ User                 │
│ Model        │                              │ 查询昨晚报警          │
│ Prompt       │                              │                      │
│ Capabilities │                              │ Agent                │
│  Skills      │                              │ 正在分析...           │
│  Tools       │                              │                      │
│  MCP         │                              │ MCP query_alarm ✓    │
│ Knowledge    │                              │ A2UI workspace ✓     │
│ Interaction  │                              │                      │
│ Permissions  │                              │ [输入测试问题...]     │
│ Advanced     │                              │                      │
└──────────────┴──────────────────────────────┴──────────────────────┘
```

### 5.1 Model

Provider 与 Model 分开选择；Tier 若保留，只作为 Automatic model selection。

展示模型能力：
- Tool Calling
- Streaming
- Reasoning
- Vision
- Responses API
- Context window / output limit

### 5.2 Prompt

保留结构化输入：
- Goal
- Guidelines
- Constraints
- Output Format
- Additional

增加 Raw / Effective Prompt 高级视图。

### 5.3 Capabilities

统一能力入口：

```text
Capabilities
├── Skills
├── Native Tools
└── MCP
```

用户不需要理解 `subSkills`、`toolConfigs` 等内部字段。

## 6. MCP 交互重构

### Agent Studio → MCP

负责“当前 Agent 使用哪些 MCP”：

- 选择已有 MCP Server
- 展示 Online / Offline / Disabled
- 展示 Tools / Resources / Prompts / MCP Apps
- 绑定 / 解绑
- 后续支持 MCP Tool whitelist
- 支持“新建 MCP Server”后返回并直接绑定

### Resources → MCP Servers

只负责 MCP Registry：

- URL
- Transport
- Authentication
- Tenant / Platform scope
- Health
- Discovery
- Tools / Resources / Prompts
- MCP Apps
- Used by Agents

MCP Admin 不再以“选 Skill 再绑定”为主操作。

## 7. A2UI / Interaction

统一放到 Interaction 页面：

- Enable A2UI
- Default Surface：Chat / Workspace / Sidebar / Modal
- Update Mode：Replace / Patch
- Allow Surface Context Writes
- Allow Action Triggered Runs
- Voice
- Welcome
- Starter Prompts

底层继续映射现有 `skillMetadata.toolConfigs.a2ui`。

## 8. Knowledge

产品层统一称为 Knowledge，不再让用户首先看到 Bucket Browser。

入口支持：
- Documents
- Folder
- Knowledge Base
- 后续 Database / External Source

第一阶段继续兼容现有 welcome.bucketBrowser 和 documents API。

## 9. Permissions

权限页面必须展示最终生效结果，而不只是配置源：

```text
Agent capability ceiling
∩ Tenant policy
∩ Group policy
∩ User permission
= Effective runtime access
```

展示：
- Visibility
- Tenant / Group / User
- Model effective access
- Tool effective access
- MCP effective access
- Knowledge effective access

## 10. Chat

主聊天页只展示 user-facing Agents。

内部 Skill / Tool / Demo 分流到：
- Resources
- Developer

Chat 页面建议：
- 左侧 Conversations
- 中间 Chat / A2UI
- 顶部 Agent 名称 + New Chat
- 管理入口不与使用入口混杂

## 11. Overview

首页只回答三个问题：

1. 我有哪些 Agent？
2. 平台当前是否正常？
3. 最近发生了什么？

主要区块：
- Agent count / active status
- MCP health
- Model Provider health
- Sessions / Usage
- Recent activity
- Quick actions

## 12. Resources

统一管理可复用资源：

```text
Resources
├── Skills
├── Tools
├── MCP Servers
├── Models
├── Knowledge
└── Secrets
```

每个资源都应支持：
- 搜索 / 分类
- 状态
- Used by Agents
- 权限范围
- 快速进入配置

## 13. Developer

将当前 Demo / Workshop / Experimental 能力收口到 Developer：

- Playground
- A2UI Playground
- MCP Apps Playground
- Protocol Inspector
- Demo Skills
- Experimental Skills

普通用户默认不显示。

## 14. 路由规划

```text
/

/agents
/agents/new
/agents/{id}
/agents/{id}/model
/agents/{id}/prompt
/agents/{id}/skills
/agents/{id}/tools
/agents/{id}/mcp
/agents/{id}/knowledge
/agents/{id}/interaction
/agents/{id}/permissions
/agents/{id}/advanced

/chat/{agentId}

/resources/skills
/resources/tools
/resources/mcp
/resources/models
/resources/knowledge
/resources/secrets

/admin/tenants
/admin/users
/admin/groups
/admin/permissions
/admin/usage
/admin/audit
/admin/settings

/developer
/developer/a2ui
/developer/mcp
/developer/protocols
```

旧 `/skills/studio/*` 保留兼容跳转，第一阶段不破坏现有 API / Runtime。

## 15. UI 视觉原则

风格：现代、克制、专业、科技感。

- 深色 / 浅色双主题
- 少用高饱和大面积渐变
- 紫蓝只用于关键 CTA / Agent 状态
- 大留白、明确层级
- 统一卡片圆角和间距
- 健康状态统一 Green / Amber / Red / Gray
- 科技感来自实时状态、协议链路和交互反馈，不靠大量发光边框

## 16. 实施顺序

### Phase 1 — 产品语义收口
- exposure / user-facing 语义
- Agent Switcher 只展示 user-facing
- Agents 列表
- Demo / internal Skill 分流

### Phase 2 — Agent Studio 核心闭环
- Studio Shell
- Basic / Model / Prompt
- Skills / Tools
- MCP Binding
- MCP Registry 职责收敛

### Phase 3 — 平台化体验
- Knowledge
- A2UI / Interaction
- Permissions / Effective Access
- Test / Preview

### Phase 4 — 收尾
- Developer Mode
- 旧页面迁移
- Browser E2E
- Legacy UI 清理

## 17. 设计原则总结

> Agent 是用户看到的产品；Skill、Tool、MCP、Knowledge 是 Agent 使用的资源；Administration 负责治理；Developer 负责实验。

该原则应作为 #74 后续所有 Feature 拆分和 UI 实现的共同约束。
