# 真实 Provider、MCP 与双租户验收

真实模型验收不能用 mock、固定 ToolCall、语法检查或预置表单代替。产品配置顺序见[完整配置流程](configuration-guide.md)，协议契约见[协议验收](protocol-operation-acceptance.md)。

## 1. 配置工作流

1. 在仓库 Actions secrets 设置 `REAL_PROVIDER_API_KEY`，不放入 workflow inputs、Issue 或提交。
2. 进入 Actions 的 `Real Provider Agent MCP acceptance`，选择待验提交/分支运行。
3. 输入 `provider_base_url`（含 API 前缀）、`model_api_name`（真实远端名）、`supports_reasoning`（按端点探测参数要求选择）。
4. 查看实际 `real-provider-agent-mcp` job，不能只看语法 job。

自动 `Protocol operation acceptance` 使用仓库变量 `REAL_PROVIDER_BASE_URL`、`REAL_PROVIDER_MODEL` 及同名 secret。端点需支持 `/models`、`/chat/completions` 和流式工具调用，并对 runner 可达；私网需合适网络的 runner。工作流会产生真实模型费用。

## 2. 浏览器链路

隔离 Compose 启动 PostgreSQL、local JWT、后端、前端、独立源沙箱和真实地图 MCP。`frontend/e2e/provider-agent-mcp-live.spec.js` 注册并探测动态 Provider/模型，通过 Root 设置选择/保存模型，再从正常 Root 对话完成：

- 真实模型选择并执行 `show-map`，渲染 MCP App，继续生成工具结果后的回复。
- 独立 surface-action-run 的 AG-UI 流和状态写入。
- 模型经校验工具输出 A2UI 表单，浏览器输入/点击、patch、刷新恢复、再次操作及回到普通聊天。

表单验收使用受约束的明确指令，不代表任意模型能稳定生成任意布局。仅 iframe 挂载也不能代替完整模型与操作链路。

每次使用独立随机资源名，并在结束时清理测试栈/卷。不要把这些会清理数据的 CI 启动和清理步骤直接用于生产。

## 3. Tenant A/B 真实额度验收

运行 `Tenant A/B real Provider acceptance`，输入相同类型服务信息和 secret。工作流配置 `BUDGET_ENFORCER=tenant-repository`，运行 `scripts/smoke-tenant-provider-acceptance.mjs`，并主动开启受测 Root 租户覆盖的 `budgetEnabled`。

夹具允许指定 `TENANT_E2E_MODEL_A/B`、`TENANT_E2E_QUOTA_USD_A/B`。模型需有有效价格，真实响应需有用量；只有预留投影或零费用不能证明实际额度消费。

| 验收项 | 必须结果 |
| --- | --- |
| 同 UID 身份 | 两个账号 UID 相同、stable tenant 不同 |
| 实际调用 | 两租户分别成功执行自己的 MCP 工具 |
| 用量 | 独立账本均有正的真实消费 |
| 跨租户能力 | 请求其他租户私有 capability 返回 404 |
| 管理边界 | 租户管理员不能提高/清空平台额度 |
| A 超额 | 不带 Skill/capability hint 的普通 Root 聊天在工具调用前返回 `BUDGET_EXCEEDED` |
| B 独立可用 | A 超额后 B 仍成功调用自己的工具 |

非模型 `scripts/smoke-tenant-isolation.sh` 另行覆盖 Session、文件、模型、MCP、审计等作用域；它本身不产生模型消费证据。

## 4. 已有证据和剩余范围

v1.1.1 的[协议操作工作流](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)中，真实浏览器和真实 A/B Provider job 均成功；正式镜像见[发布工作流](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)，同为 `29688543e0b4c1749210a8be90b0c94a207ca87e`。

留存运行 URL、提交 SHA、Provider/模型、job 结果和脱敏证据，及时下载所需 artifact，凭证不进入记录。PR 只做语法检查时不能报告真实验收通过。

这些工作流不证明目标部署旧数据已经迁移，也不自动验证目标代理下的失败/截断/取消路径。目标环境仍执行[迁移手册](tenant-ownership-migration.md)及完整协议复验，[Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 保持其现场验收边界。
