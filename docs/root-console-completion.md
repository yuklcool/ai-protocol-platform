# Agent 与用户配置

| 配置 | 归属 | 管理入口 |
| --- | --- | --- |
| 模型、系统提示、原生工具、MCP、公共 Skill、公共知识 | Agent | Root Agent 设置 |
| 个人 Skill 绑定、个人信息和偏好 | 用户 | 账号菜单 → 个人 Skill 与信息 |
| 账号启用状态、密码 | 用户账号 | 用户管理 |
| 私有文件、会话、记忆、Artifact | 用户 | 聊天与文件接口 |

Agent 公共绑定和当前用户的个人 Skill 合并后组成能力目录。调用 `load_skill` 时重新检查当前绑定和资源 ACL。个人配置不授予工具、MCP 或模型权限。

管理员账号也可编辑个人配置。管理员身份仅影响平台管理接口；普通用户只能读取和修改自己的个人配置。

`GET/PUT /api/auth/profile` 使用当前身份。`GET/PUT /api/admin/accounts/{email}/profile` 仅管理员可用。个人 Skill 必须属于目标用户；账号和密码不会写入个人信息或审计快照。

用量统计按用户和模型归集输入/输出 Token 与估算费用。通用预算执行器保留 `off` 与 `in-memory` 模式，用户信息中不能配置额度或绕过控制。

完整操作见 [配置流程](configuration-guide.md)。
