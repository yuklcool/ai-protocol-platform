# 本地体验与协议学习

本地运行步骤统一维护在 [SELFHOST：本地源码开发](SELFHOST.md#11-本地源码开发)。生产方式的持久化体验使用[完整配置流程](docs/configuration-guide.md)中的 Compose 部署。

`make dev-local` 同时启动后端和前端，不要另起一个前端进程。开发模式使用本地认证和存储替身；模型调用仍需有效凭据。它不证明生产认证、持久化或历史数据升级。

建议按以下顺序阅读当前实现：

1. [模块边界](docs/module-simplification.md)：Root、Skill、工具和权限。
2. [代码导览](docs/workshop/code-tour.md)：产品请求到 ADK/AG-UI 的入口。
3. [协议验收](docs/protocol-operation-acceptance.md)：A2UI 操作与刷新恢复。
4. [真实模型验收](docs/real-provider-acceptance.md)：Provider、工具和双租户验证。
5. [附件分析](docs/chat-file-analysis.md)：格式、选择、来源及失败边界。

[历史版本设计](docs/archive/design/README.md)用于理解演进；旧课程截图、步骤和版本状态应结合当前实现核对。
