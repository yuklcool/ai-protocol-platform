# 当前代码导览

平台使用一个面向用户的 Root Agent。Skill 是授权后延迟加载的内容能力；完整运行约束见[模块边界](../module-simplification.md)。

| 顺序 | 代码入口 | 阅读重点 |
| --- | --- | --- |
| 1 | [Root 组合](../../backend/agents/root_runtime.py) | 平台配置、个人能力组合、模型和能力上限 |
| 2 | [应用与流入口](../../backend/fast_api_app.py) | `/api/agent/stream`、认证及协议路由 |
| 3 | [单轮处理](../../backend/skills/skill_processor.py) | 授权、会话、Agent 创建和事件流 |
| 4 | [ADK 工厂](../../backend/adk/agent.py) | 模型路由、工具解析、回调组合 |
| 5 | [AG-UI 适配](../../backend/adk/agui.py) | ADK 与 SSE 运行事件 |
| 6 | [前端订阅](../../frontend/src/hooks/useSkillAgent.ts) | 消息、工具、运行状态和错误恢复 |
| 7 | [聊天表单入口](../../frontend/src/components/chat/ChatMessageList.tsx) | A2UI 表面与消息按时间交错 |
| 8 | [MCP 代理](../../backend/protocols/mcp_proxy.py) | 服务选择、授权和协议转发 |
| 9 | [附件解析](../../backend/tools/documents/parsing.py)与[读取](../../backend/tools/documents/access.py) | 本地文本、来源位置和本轮授权选择 |

`backend/app.py` 提供 ADK/A2A 入口；产品 Root 对话的有效模型和权限需沿上表中的请求路径核对。当前行号随代码变化，不在文档维护固定行号或 LOC。

验证从[协议验收](../protocol-operation-acceptance.md)、[真实 Provider 验收](../real-provider-acceptance.md)和[附件分析说明](../chat-file-analysis.md)进入。历史演进见[版本设计归档](../archive/design/README.md)。
