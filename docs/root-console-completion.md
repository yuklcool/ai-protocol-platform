# Root Agent 控制台操作闭环（#111）

首次配置请按[完整中文配置流程](configuration-guide.md)操作；本文说明各控制台功能及其边界。

本版本补齐知识检索、普通 Root 对话额度控制、租户策略、工具授权、本地账号和用量统计。继续使用现有 Repository / PostgreSQL 与文件存储，不增加向量数据库、缓存服务或任务队列。

## 配置与操作

1. **Models**：注册 Provider 和模型，执行连通性及工具调用探测。自定义模型可同时填写输入、输出美元 / 百万 Token 价格；未知价格会明确标为未计价。有额度上限的租户使用未计价模型时会在调用前拒绝。
2. **租户**：使用稳定租户 ID 创建租户，身份域可留空。平台管理员配置模型白名单、默认模型、额度周期和提醒阈值；租户管理员不能提升或清空这些限制，也不能通过派生标签提升管理权限。
3. **租户 Agent 策略**：按租户覆盖模型、指令、Skills、Tools、MCP 和知识绑定。未设置的字段继承平台配置；自定义空列表表示不绑定资源。保存不会改变其他租户策略；运行时继续检查资源权限。
4. **Root Agent → 知识**：上传并等待解析完成，将资料创建为私有或同租户可检索的知识来源，选中后保存 Root 配置。检索预览使用已保存配置。运行时的 `search_agent_knowledge` 返回来源名称、摘录及位置，每次都重新检查租户、资料归属和来源 ACL。修改共享范围或删除来源立即生效，原文件下载权限保持原有规则。
5. **Root Agent → 租户额度**：主动启用后，每次 Root 模型调用（包括未加载 Skill 的普通聊天与 action-run）均执行持久化租户预算回调。Root 直接创建 `TenantRepositoryBudgetEnforcer`，不依赖环境变量 `BUDGET_ENFORCER` 开启；该环境接口继续兼容旧 Skill/外部注册。能力包不能将其改为用户额度或声明免计费。额度为 0 表示不限额；缺失租户、无效配置或缺失价格时，有上限的调用失败关闭。
6. **Root Agent → 交互**：语音开关控制朗读配置，关闭后拒绝合成。默认使用浏览器语音，不需要 GCP；其他服务端语音提供者通过部署环境配置。部署级 `NEXT_PUBLIC_ENABLE_READ_ALOUD=false` 可禁用朗读。浏览器需要提供 Speech Synthesis 支持及可用语音。
7. **Tools**：支持用户、稳定租户、旧域名和全局规则，稳定租户键为 `tenant:<id>`。租户策略是上限，用户规则不能绕过它；权限预览使用相同归属及上限规则。
8. **用户**：local JWT 的平台管理员可创建、停用、重新启用、调整租户和重置密码。敏感更改撤销旧 JWT；分组修改逐请求生效。权限预览和分组成员查询也使用本地目录。Firebase 保留原接口与刷新语义；OIDC 明确交由外部身份提供者管理，不伪装为本地账号管理。
9. **用量**：按时间和租户查看 Provider 返回的输入 / 输出 Token、调用数、估算成本、未计价调用以及当前额度周期的已计费和预留。只从此版本之后累计，不回填历史、不存储对话正文；费用不是供应商结算账单，未返回用量的调用不计入统计。

知识检索是现有解析文本上的关键词检索，最多扫描每个来源前 200 万字符，返回有界摘录；不声称提供语义向量检索或扫描图片 OCR。存储继续按现有租户隔离规则运行；控制台不提供无法生效的命名空间迁移按钮。

## 验证与发布

- 后端：`uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest tests/ --ignore=tests/integration -m 'not slow'`。
- 前端：`npm run quality:check`。
- 新增 API 回归：`backend/tests/api_tests/test_root_console_completion.py`，覆盖普通 Root 预算回调、账号会话撤销、同 UID 跨租户隔离、知识撤权、权限预览、价格和权限提升防护。
- `Model provider gate` 在真实 PostgreSQL / 后端 / 前端上运行 `frontend/e2e/root-console-live.spec.js`，不拦截浏览器 API。覆盖租户策略、权限规则、账号、角色导航、文件上传、检索及移动端；截图作为 CI artifact 保存。
- 现有 `Protocol operation acceptance` 继续运行真实 Provider → AG-UI → MCP / A2UI action-run 与租户隔离验收。A2UI 支持范围仍为 v0.9 SDK basic catalog，AG-UI 使用仓库锁定的 SDK；参见 [协议操作验收](protocol-operation-acceptance.md)。
- 发布候选在相同提交的 CI、持久化、模型与控制台、A2UI、真实 Provider 协议验收全部成功后才允许打标签和启动镜像发布。候选配置或代码提交不代表镜像已发布。
- [v1.1.1 已正式发布](https://github.com/yuklcool/ai-protocol-platform/releases/tag/v1.1.1)，对应提交 `29688543e0b4c1749210a8be90b0c94a207ca87e` 的功能验收及[镜像扫描、匿名拉取、全新环境启动 / 登录](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)全部成功。环境文件资产名为 `default.env.selfhost.example`，下载后保存为 `.env`；参见[部署步骤](selfhost-release-images.md)。v1.1.0 的失败发布未生成正式 Release，原标签保留。Sandbox 的平台无关 JavaScript 改为构建机原生编译，生产依赖与 Node 运行时继续按目标架构构建。

## 目标部署边界

本轮没有生产环境地址、访问凭证或历史数据快照。#9 的目标环境迁移、备份恢复、迁移回滚和最终现场验收必须在实际部署上执行；该问题保持开放，不能用本地或 CI 通过替代。参见 [Self-host 部署](../SELFHOST.md)。
