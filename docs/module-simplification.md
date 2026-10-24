# 平台模块与配置边界

平台使用一个面向用户的 Root Agent、一个对话/工作台和一条协议运行链路。登录后进入 `/workspace` 稳定工作台；`/sessions` 恢复真实历史，`/results` 按来源会话查找成果摘要。Root 在 `/agent` 配置，内容能力在 `/skills` 发现、个人启用与使用，实际运行仍进入 `/chat/root-agent`，不引入第二套 Agent 运行时。逐步说明见[配置手册](configuration-guide.md)。

## 1. Root 与 Skill

Root 决定模型、指令、工具、MCP、知识和交互。Skill 编辑器只管理名称、描述、指令、参考资料、资源文件及访问控制；不创建独立的第二个 Agent 或测试聊天。

修改旧 Skill 内容仅提交内容字段。旧模型、工具、委派、persona、welcome、shell 和协议字段保留存储以兼容 API，但不作为独立 Agent 配置。运行权限仍由 Root、可信用户/用户策略及资源 ACL 限制。

参考/资源文件通过授权单资源接口读取，目录列表不批量返回文件正文。编辑器拒绝重复/空文件名。

## 2. 当前保留能力

保留 A2UI、AG-UI、MCP/MCP Apps、文档、Session/Memory、认证、用户隔离、模型策略、额度、审计和自托管发布检查。协议诊断页面保留为开发验收入口，不进入普通产品导航。普通导航收敛为工作台、历史对话、我的成果、能力中心；管理员从就绪与资源接入总览进入 Root、模型及 MCP 配置，原资源 URL 保留。

成果列表只读取当前所选授权会话的 A2UI 状态摘要，不扫描对话全文，不包含附件或管理员原生 Artifact 下载。资源可见、已绑定、模型已验证、目标账号实际可用分别呈现，不相互替代。

知识绑定在 Root 设置中配置，文件上传/查看使用真实工作台能力；没有独立假数据知识库。可选消息通道只在对应凭证启用时加载，普通 Web 部署不初始化 Discord、Telegram、Mailgun 或 Twilio。

## 3. 已移除实现

移除旧 Skill 切换栏、未使用分栏/预算横幅/只读输入框、Skill 独立模型与工具编辑、重复测试聊天及创作 Copilot、硬编码文件/富媒体演示和未使用依赖。

旧 `/agents`、`/agents/:id`、`/skills/new`、`/dev/file-browser`、`/dev/rich-media` 和 `/workshop` 不再提供兼容跳转。使用当前 `/agent`、`/skills/studio/new` 及本文列出的产品入口；自托管步骤见 [SELFHOST](../SELFHOST.md)。

删除没有产品调用者的旧 AG-UI 路由挂载器、Skill 临时文件转换器、未注册的 RAG FunctionTool 和语音 Agent 空文件。对话继续通过 `fast_api_app.py` → `skills/skill_processor.py` → `adk/agui.py` 运行；RAG 管理 API 仍通过 `tools/documents/rag_routes.py` 调用 `rag/corpus.py`。

删除空的 after-agent 回调、搜索工厂的重复包装、未调用的计数与身份辅助函数和旧常量别名。搜索验收直接调用生产使用的 Web/Enterprise 工厂；AG-UI 的用户身份与会话保留回归继续覆盖实际聊天构建器。测试使用的缓存重置、注册表一致性检查及动态加载的 ADK 服务入口保留。

`LOCAL_MODE_PERSIST` 从未接入持久化实现，现移除其配置示例、读取函数和错误提示。`LOCAL_MODE` 的内存数据在重启后清空；持久化部署使用已支持的 PostgreSQL/对象存储配置。

本轮模块整理不执行生产迁移；旧 ADK Session/Memory namespace 仍按 [Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 验收。
