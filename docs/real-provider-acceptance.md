# 真实 Provider、MCP 与用户隔离验收

在仓库变量中设置 `REAL_PROVIDER_BASE_URL`、`REAL_PROVIDER_MODEL`，并设置 Actions secret `REAL_PROVIDER_API_KEY`。默认验收模型为 `gpt-6-luna`。测试密钥只通过运行环境传递。

真实 Provider 浏览器工作流验证普通生成、工具调用、MCP Apps、A2UI 操作与刷新恢复。公共配置直接写入 Agent，用户信息和个人 Skill 使用 `/api/auth/profile`。

两个不同 UID 的账号应分别拥有个人 Skill、信息、文件、Session 和 Memory。公共绑定均可使用，私有绑定只对所有者生效；不能通过猜测资源 ID 或伪造用户字段跨用户读取。

本地 `test_user_profiles.py`、文档模型输入探针及 ADK 用户作用域测试验证确定性边界。PostgreSQL、真实 Provider 和浏览器测试需要相应运行环境；分别记录提交和工作流结果。

旧组织数据直接清理，执行方式见 [配置流程](configuration-guide.md#7-旧部署升级)。不再执行组织数据迁移、模型白名单或额度账本验收。
