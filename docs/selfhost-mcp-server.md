# MCP 服务与 MCP Apps 配置

通过 `/admin/mcp-servers` 管理持久化服务注册表，无需直接编辑数据库。普通产品路径由 Root Agent 统一绑定和调用，见[完整配置流程](configuration-guide.md#7-skill原生工具与-mcp)。

## 1. 注册服务

填写稳定服务 ID、backend 可达 URL、服务要求的传输方式和作用域，启用并保存。私有集成选择 Tenant；明确共享的服务才选择 Platform，后者需要平台管理员权限。租户管理员只能管理自己的作用域。

HTTP/SSE/Streamable HTTP 按实际服务契约选择。容器中的 `localhost` 不能访问另一个容器；Docker 服务名也不是浏览器能直接解析的公共 URL。

## 2. 凭证

请求头值只写入，接口/界面仅回显名称和是否已配置。优先环境引用：

```text
Authorization=${MCP_TOKEN}
X-Api-Key=${MCP_API_KEY}
```

若服务要求 Bearer，可将变量值设为带 `Bearer ` 前缀的完整头值，或按服务表单支持格式填写。变量在建立传输前解析，缺失时拒绝调用。

自定义变量需要在 backend 的 Compose `environment` 中显式传递，只有 `.env` 中定义并不够，见[变量示例](configuration-guide.md#10-可选配置与环境变量传递)。编辑时留空保留旧头，选择“保存时清除所有请求头”才移除。

## 3. 健康与能力发现

“健康检查”执行 MCP `initialize`，不是只测 TCP。错误分类：

| 分类 | 排查方向 |
| --- | --- |
| `network` | DNS、连接、超时 |
| `authentication` | HTTP 401/403、头值与权限 |
| `protocol` | MCP/传输行为不兼容 |
| `schema` | 返回结果不符合结构 |
| `configuration` | 本地设置或密钥引用无效 |

“发现”查询 `tools/list`、`resources/list`、`prompts/list` 和 UI 资源。资源/提示词是可选能力，未提供时可能只返回警告。管理员可测试禁用服务，但 Agent 和浏览器代理均不能正常使用禁用服务。

## 4. Root 绑定和工具权限

在 `/agent` 的“MCP”勾选服务，保存；在工具规则允许实际发现的工具，并检查租户归属和 Root 权限。使用 `/chat/root-agent` 提出具体任务，观察模型真实选择和执行工具。

管理页保留“绑定 Skill”的兼容操作，写入旧 `skillMetadata.toolConfigs.mcp.servers`。它不替代当前 Root 的显式绑定，也不会绕过 Skill 或工具权限。

## 5. MCP Apps 浏览器验证

工具返回 UI 资源后，通过平台认证代理 `/mcp/{server_id}` 获取内容，再由独立源沙箱承载。需配置：

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
```

确认前端调用、代理访问、`ui://` 读取、iframe 渲染均成功。禁用服务后重试，应在运行时和代理两侧拒绝。

## 6. 可选地图示例

示例仅存在于**源码 Compose** 的 `mcp-example` profile，发布 Compose 没有该服务。请在隔离测试部署使用：

```bash
docker compose --profile mcp-example up -d --build
```

注册 URL `http://mcp-example-map:8080/mcp`，传输选 Streamable HTTP。示例暴露 `show-map` 和 `ui://cesium-map/mcp-app.html`，仅在内部网络监听，不发布主机端口。

绑定 Root、授权后发起地图请求，确认实际 Tool Calling 和 App 渲染。发布部署需要单独部署可达 MCP 服务，不能直接引用不存在的示例主机名。
