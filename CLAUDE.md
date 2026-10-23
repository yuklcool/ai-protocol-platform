# 开发协作约定

本仓库为 `yuklcool/ai-protocol-platform`。当前产品与操作入口见 [README](README.md)、[配置流程](docs/configuration-guide.md)及[模块边界](docs/module-simplification.md)。历史上游设计见[归档](docs/archive/design/README.md)，其中的账号、默认分支、GCP 环境和待办状态不作为当前操作指令。

## 架构

- 一个面向用户的 Root Agent；模型、工具、MCP、知识、权限和交互由 Root 统一配置。
- Skill 复用指令、参考资料和资源；按授权延迟加载，不恢复旧的独立 Agent 编辑流程。
- 默认自托管使用 Next.js、FastAPI/Google ADK、PostgreSQL、本地对象及 Artifact 卷、独立源 MCP Apps 沙箱；云服务按显式配置启用。
- AG-UI 传递运行事件，A2UI v0.9 与 SDK basic catalog 渲染表面；工具结果复用现有注册映射。

## 数据与权限

- 保持服务端用户归属、资源 ACL 和 Root 能力上限校验；客户端提交的用户或文档 ID 不构成授权。
- 私有文件、截图、缩略图、内容片段及其派生结果必须经原资源的授权边界提供，不能改成公开桶或公开链接。
- 密钥只从部署环境解析；代码、日志、文档和测试产物不保存实际凭据或客户内容。
- 上传、解析和模型读取分别验证。不可读附件在调用模型前拒绝，不能生成虚假分析成功。
- 旧租户迁移方案已由 PR #135 替代，Issue #9 按 not_planned 关闭；当前采用用户归属与旧组织数据清理规则，见配置流程。全新环境通过不代表目标部署已升级。

## 实现约定

- 模型通过 `resolve_model_chain` 或既有 `generate_content_resilient` 调用；避免叠加 SDK 重试层。
- 工具结果通过 `a2ui_result_render` 注册映射；需要表单交互时复用 A2UI 和 SurfaceRegistry。
- API 使用认证客户端 `fetchWithAuth`；独立 MCP Apps 源与消息桥接保持有效。
- 页面提供明确的加载、空、错误、权限拒绝和取消反馈；操作控件使用可读标签和键盘焦点。
- 删除已停用实现及其孤立测试；必要回归移到实际产品入口，不添加没有使用者的兼容包装。
- 多步开发工作流优先使用现有脚本或 Make 目标，避免在多份文档复制维护相同部署步骤。

## 开发与验证

| 工作 | 命令 |
| --- | --- |
| 开发依赖 | `cd backend && uv sync --dev`；`cd frontend && npm ci` |
| 本地开发 | 按 [SELFHOST](SELFHOST.md#11-本地源码开发) 配置后运行 `make dev-local` |
| 生产方式自托管 | 按配置流程运行 Docker Compose |
| 后端质量 | `cd backend && make lint && make test-fast` |
| 前端质量 | `cd frontend && npm run quality:check` |
| 文档链接 | `make link-check` |
| ADK 升级 | `make adk-conformance`，同时核对桥接版本和真实运行链路 |

快速 lint/typecheck 不替代单元测试、构建或适用的 PostgreSQL/浏览器/真实 Provider 验收。运行后端命令使用项目 `uv` 环境。改动依赖时同步锁文件。

## 提交与交付

使用独立分支和可审查 PR；提交信息采用 conventional commits。合并前检查提交本身的 CI 与必要协议验收，不以其他提交的结果替代。不要重写部署快照或受保护分支。合并、发布和目标部署升级分别记录状态。

后端细则见 [backend/CLAUDE.md](backend/CLAUDE.md)；A2UI、流式事件与压缩机制见 [backend/adk/CLAUDE.md](backend/adk/CLAUDE.md)。
