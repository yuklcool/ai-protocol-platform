# Development Planning Governance

本项目使用 **Roadmap → Milestone/Version → Epic → Feature/Task → Pull Request** 的方式管理后续开发。

这套规则从新的开发需求开始执行；历史已完成 Issue 不做大规模重拆，避免破坏既有审计、PR 和 CI 证据链。

## 1. 层级定义

### Roadmap

Roadmap 只维护长期方向、当前阶段、版本目标和关键入口，不承载每个需求的详细实现记录。

当前顶层 Roadmap：[#15](https://github.com/yuklcool/ai-protocol-platform/issues/15)。

### Milestone / Target Version

Milestone 表达一个可交付版本或阶段，例如：

- v1.0.x — Self-host Foundation
- v1.1 — Platform Productization
- v1.2 — Agent Ecosystem

一个 Milestone 中包含多个 Epic / Feature Issue。Milestone 完成意味着该版本定义的验收条件已满足，而不是“代码写完”即可。

> GitHub Milestone/Project 仅作为管理元数据；功能真实性仍以 PR、CI、E2E 和真实环境验收为准。

### Epic

Epic 是一组有统一业务目标的大型能力，通常不能通过单个 PR 完成。

例如：

- Agent 管理体系
- Skill 生命周期管理
- Knowledge Base / RAG
- Observability / Usage

Epic 必须列出：

- 背景与目标
- 用户场景
- 范围 / 非范围
- 子 Issue
- 依赖
- 完成条件

### Feature

Feature 是最重要的交付单元：一个可以独立实现、测试和验收的产品能力。

Feature 应满足：

- 目标明确
- 边界明确
- 有验收标准
- 能关联一个或多个 PR
- 完成后可以明确 Close

### Task

Task 用于 Feature 内部仍需独立跟踪的实现工作，例如：

- 数据库 migration
- Backend API
- Frontend 页面
- E2E/Acceptance gate
- 文档

不要为了“拆而拆”。如果一个 Feature 可以由一个 PR 清晰完成，就不需要额外 Task。

### RFC

对架构影响较大、方案尚未确定的需求先建立 RFC，而不是直接进入开发。

适用场景：

- 新协议或协议扩展
- 数据模型大改
- 多 Agent runtime
- 新基础设施依赖
- 安全边界/租户模型变化

RFC 被接受后，再拆 Epic / Feature Issue。

## 2. Issue 生命周期

建议状态流：

```text
Backlog
  ↓
Ready
  ↓
In Progress
  ↓
Review
  ↓
Testing / Acceptance
  ↓
Done
```

Issue 关闭前必须满足其“验收标准”。PR merge 不自动等于产品验收完成；涉及真实 Provider、Tenant、MCP、发布链路的能力必须保留真实验收证据。

## 3. Pull Request 与 Issue 关联

Feature / Task PR 必须在 PR 描述中使用明确关系：

```text
Closes #123
```

如果 PR 只是 Epic 的一部分：

```text
Part of #120
Closes #123
```

不要用 PR 直接关闭仍有未完成子项的 Epic。

## 4. 优先级

推荐统一使用：

- P0：阻塞发布、安全或数据正确性的紧急问题
- P1：当前版本必须完成
- P2：重要增强，可在当前/下一版本排期
- P3：候选、优化或低优先级需求

优先级不替代依赖关系。被 P2 依赖的 P1 前置项仍应先完成。

## 5. Area

推荐按能力域管理，而不是按人员管理：

- backend
- frontend
- agent
- skill
- mcp
- provider
- auth
- tenant
- storage
- observability
- infra/release

## 6. Definition of Done

Feature / Task 只有在适用条件全部满足后才应关闭：

- [ ] 实现已进入 main
- [ ] 单元/集成测试通过
- [ ] 相关 CI gate 通过
- [ ] 跨租户/权限/失败路径测试已覆盖（如适用）
- [ ] 真实 Provider / MCP / 浏览器 E2E 已验证（如适用）
- [ ] migration / rollback 已验证（如适用）
- [ ] 文档已同步
- [ ] 没有把已知阻塞项留在关闭 Issue 中
- [ ] 验收证据已链接到 Issue/PR

## 7. 历史 Issue 迁移原则

现有自托管改造 Issue 保持原编号、原讨论和原证据链，不重新创建重复 Issue。

- 已关闭：保持关闭，不重拆。
- 仍开放：继续按原验收标准收口。
- 新需求：使用 Epic / Feature / Task / RFC 模板。
- Roadmap #15：只维护版本级状态和导航，不继续堆叠每个 PR 的实现细节。

## 8. GitHub Project 推荐字段

如果启用 GitHub Projects，推荐字段：

| Field | Values |
| --- | --- |
| Status | Backlog / Ready / In Progress / Review / Testing / Done |
| Priority | P0 / P1 / P2 / P3 |
| Type | Epic / Feature / Task / Bug / RFC |
| Area | Agent / Skill / MCP / Provider / Auth / Tenant / Infra / ... |
| Target Version | v1.0.x / v1.1 / v1.2 / ... |
| Start Date | date |
| Target Date | date |

推荐视图：

1. Development Board — 按 Status 看执行流
2. Roadmap — 按 Epic + 日期看时间线
3. Backlog — 看尚未排期需求
4. Release View — 按 Target Version 看版本范围

## 9. 规划变更原则

新增需求时：

1. 先判断是否需要 RFC。
2. 判断属于现有 Epic 还是新 Epic。
3. 明确 Target Version 和 Priority。
4. 拆成可独立验收的 Feature。
5. 只有复杂 Feature 才继续拆 Task。
6. 开发 PR 必须回链 Issue。
7. 验收后关闭 Feature/Task；Epic 在所有必需子项完成后关闭。

这样可以避免“Roadmap 写得越来越长，但不知道下一步该做什么”的问题。
