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

## 3. 已移除和兼容入口

移除旧 Skill 切换栏、未使用分栏/预算横幅/只读输入框、Skill 独立模型与工具编辑、重复测试聊天及创作 Copilot、硬编码文件/富媒体演示和未使用依赖。

旧 `/agents`、`/agents/:id`、`/skills/new` 及演示/workshop URL 通过统一 Next.js redirects 兼容。旧链接重定向不代表恢复被移除模块。

本轮模块整理不执行生产迁移；旧 ADK Session/Memory namespace 仍按 [Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 验收。
