# AI Protocol Platform

基于 Google ADK 的开源智能体应用平台，将 **Root Agent、Skills、AG-UI、A2UI、MCP、MCP Apps 与 A2A** 接入统一运行链路，支持中文界面和私有化部署。

平台只有一个面向用户的 Root Agent。模型、工具、MCP、知识和交互行为由 Root Agent 统一配置；Skill 用于复用指令、参考资料和资源文件。用户从普通对话进入，智能体可以调用工具、生成交互表单，并在刷新后恢复会话和界面状态。

**第一次使用请从[完整中文配置流程](docs/configuration-guide.md)开始。**手册按“部署 → 登录 → 模型 → 租户与账号 → Skill/工具/MCP → 知识 → A2UI → 额度 → 验收”的顺序说明在哪里配置、怎样填写以及如何确认生效。

## 功能与入口

| 能力 | 使用方式 |
| --- | --- |
| 统一智能体 | 在 `/agent` 配置模型、指令、能力绑定、权限与交互，在 `/chat/root-agent` 对话 |
| 可复用技能 | 在 `/skills` 管理指令、参考资料、资源文件和访问控制 |
| 模型接入 | 在 `/admin/model-providers` 按步骤添加模型服务、选择模型、测试并用于平台 Root |
| 交互式界面 | AG-UI 传递运行事件，A2UI 渲染表单、操作和状态更新 |
| MCP 与 MCP Apps | 服务管理、健康检查、能力发现、工具调用及独立源沙箱渲染 |
| 对话附件 | 在普通对话上传 TXT、Markdown、CSV、文本 PDF、DOCX、XLSX、PPTX；选择参与本轮分析，恢复会话附件状态 |
| 知识检索 | 上传并解析资料，在 Root Agent 中创建、绑定和检索知识来源 |
| 多租户管理 | 稳定租户 ID、账号与权限组、模型策略、租户 Root 覆盖和有效权限预览 |
| 持久化与统计 | PostgreSQL 保存业务数据、会话、记忆和用量；持久卷保存文件与 Artifact |

对话附件的配置、格式范围、故障处理和验收要求见[文件上传与分析说明](docs/chat-file-analysis.md)。附件整改属于后续源码修改，不能据此推断 `v1.1.1` 镜像已经包含。

## 运行架构

| 层次 | 组件与职责 |
| --- | --- |
| 浏览器 | Next.js / React、统一对话与工作台、AG-UI 客户端、A2UI 渲染器 |
| 应用后端 | FastAPI、身份认证、租户授权、模型/MCP 管理和协议接口 |
| 智能体运行时 | Google ADK、Root Agent、Skill 指令加载、原生工具、MCP 和 A2A |
| 数据存储 | PostgreSQL：平台配置、租户、账号、Session、Memory 和账本 |
| 文件与沙箱 | 持久卷：文件和 Artifact；独立浏览器源：MCP Apps 沙箱 |

默认部署包含 `frontend`、`backend`、`postgres`、`mcp-sandbox` 四个服务，不要求 GCP、Firebase、Redis、MinIO 或 Keycloak。

## 快速部署

以下命令用于**全新安装**。已有部署先阅读[升级、迁移与回滚](docs/configuration-guide.md#12-已有部署升级迁移与回滚)，保留现有配置和数据卷。

### 使用 v1.1.1 发布镜像

需要 Docker Engine、Compose v2，以及到 GHCR 和模型服务的网络连接。

```bash
mkdir -p ai-protocol-platform-deploy
cd ai-protocol-platform-deploy
release_version=v1.1.1
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/docker-compose.release.yml" -o docker-compose.release.yml
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/default.env.selfhost.example" -o .env
chmod 600 .env
openssl rand -base64 48
```

编辑 `.env`，至少完成下表；所有占位内容均应替换：

| 配置项 | 填写要求 |
| --- | --- |
| `APP_VERSION` | 确认为 `v1.1.1`，生产环境使用明确版本 |
| `JWT_SIGNING_KEY` | 上一步生成的随机密钥，后续重启保持稳定 |
| `SELFHOST_ADMIN_EMAIL` | 首次启动的平台管理员邮箱 |
| `SELFHOST_ADMIN_PASSWORD` | 首次管理员密码，至少 12 个字符 |
| `POSTGRES_PASSWORD` | 设置数据库密码 |
| `DATABASE_URL` | 与数据库用户、密码、库名一致，容器内主机名为 `postgres` |
| `OPENAI_API_KEY` | 使用 OpenAI 兼容服务时填写实际密钥；其他提供商见配置手册 |
| 浏览器源配置 | 本机可用默认值；远程访问按实际前端和沙箱地址设置 |

```bash
docker compose -f docker-compose.release.yml config --quiet
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
docker compose -f docker-compose.release.yml ps
```

本机打开 `http://localhost:3456`，使用首次管理员账号登录。接着在“模型”中注册 Provider 和模型，执行普通生成与工具调用探测，再到“Root Agent”选择该模型并保存。**容器健康和登录成功不代表模型已经配置完成。**

Release 模板名是 `default.env.selfhost.example`；源码模板名是 `.env.selfhost.example`。详见[版本化镜像部署](docs/selfhost-release-images.md)。

### 从源码构建

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
# 配置密钥、管理员、数据库、模型和浏览器源，保存 .env。
docker compose config --quiet
docker compose up -d --build
```

日常管理使用 `docker compose ps`、`docker compose logs --tail=100 backend` 和 `docker compose down`。停止服务时不要附加删除数据卷的参数。源码开发模式见[自托管与开发说明](SELFHOST.md)。

## 部署后的配置顺序

以下控制台流程对应当前源码。v1.1.1 发布镜像尚未包含本次模型接入改版；使用该镜像时仍需在原页面注册并测试模型，再到 Root 配置选择模型。

1. **模型**：在“模型接入”添加服务，填写 API 根地址与后端密钥变量名；读取或手动填写模型名称，测试普通生成和工具调用，通过后点击“用于平台 Root”。内部标识自动生成，单模型无需填写层级映射。
2. **租户与账号**：创建稳定租户 ID，配置模型白名单、额度和账号归属；使用权限预览核对结果。
3. **能力**：创建 Skill 内容，注册并发现 MCP 服务；通过当前 Root、租户允许资源和权限组分配给用户。
4. **Root Agent**：选择模型，绑定已授权的 Skills、Tools、MCP 和知识来源，保存配置。
5. **交互**：需要表单操作时，同时开启 A2UI、界面上下文写入和操作触发运行。
6. **额度**：配置租户额度和模型价格，主动启用 Root 预算；Root 会直接使用持久化租户执行器。
7. **验收**：普通聊天、实际工具调用、MCP App、A2UI 提交、刷新恢复和双租户隔离均通过后开放使用。

逐字段示例和排错见[完整中文配置流程](docs/configuration-guide.md)。

## 地址、域名与接口

| 用途 | 默认地址或接口 |
| --- | --- |
| 前端 | `http://localhost:3456` |
| Root 对话 | `/chat/root-agent` |
| 管理入口 | `/admin` |
| 后端接口文档 | `http://localhost:1956/docs` |
| 后端健康检查 | `GET /health` |
| 统一 AG-UI 流 | `POST /api/agent/stream` |
| 兼容 Skill 流 | `POST /api/skill/{skill_id}/stream` |
| 当前身份 | `GET /api/auth/whoami` |
| MCP Apps 沙箱 | `http://localhost:3457/sandbox.html` |

远程部署应将前端和沙箱分别映射到两个浏览器源，例如 `https://ai.example.com` 与 `https://mcp.example.com`，并设置 `ALLOW_ORIGINS`、`MCP_SANDBOX_PUBLIC_URL`、`MCP_SANDBOX_ALLOWED_HOST_ORIGINS`。浏览器中的 `localhost` 不是远程服务器地址。

## 版本状态与升级边界

v1.1.1 发布基线为 `29688543e0b4c1749210a8be90b0c94a207ca87e`：

- [正式 Release](https://github.com/yuklcool/ai-protocol-platform/releases/tag/v1.1.1)：三个应用镜像支持 `linux/amd64` 和 `linux/arm64`。
- [镜像发布验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)：构建、扫描、匿名拉取、全新环境启动和管理员登录成功。
- [真实 Provider 与协议验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)：真实 MCP 调用、A2UI 操作/刷新恢复及 A/B 租户额度隔离成功。

上述记录证明发布和受测环境能力。**已有部署的历史 ownership、ADK Session、Memory namespace 迁移与回滚仍由 [Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 跟踪，不能用全新安装成功代替。**

当前 A2UI 支持范围为 **v0.9 + SDK basic catalog**；AG-UI 后端桥接锁定 `ag-ui-adk==0.6.5`、`google-adk==1.31.1`。知识检索为解析文本上的关键词检索，用量费用是估算值。

## 中文文档导航

| 文档 | 内容 |
| --- | --- |
| [完整配置流程](docs/configuration-guide.md) | 首次部署到业务可用的操作、参数解释与排错 |
| [自托管说明](SELFHOST.md) | 部署方式、认证、持久化和日常运维 |
| [版本化镜像部署](docs/selfhost-release-images.md) | 下载、版本、镜像来源、升级与回滚 |
| [模型接入](docs/selfhost-openai-compatible.md) | 地址、密钥引用、模型 ID、能力与价格 |
| [MCP 配置](docs/selfhost-mcp-server.md) | 注册、凭证、健康检查、发现、绑定和验证 |
| [Root 控制台](docs/root-console-completion.md) | 知识、账号、租户策略、预算和用量边界 |
| [协议验收](docs/protocol-operation-acceptance.md) | A2UI / AG-UI 操作验收 |
| [真实 Provider 验收](docs/real-provider-acceptance.md) | 真实模型和 A/B 租户工作流 |
| [历史归属迁移](docs/tenant-ownership-migration.md) | dry-run、审核、apply、verify 和 rollback |
| [OIDC 接入](docs/selfhost-oidc.md) | 企业认证与显式账号关联 |
| [OIDC 示例](docs/oidc-providers.md) | Keycloak、Entra ID 和 Okta |
| [S3 兼容存储](docs/s3-object-storage.md) | 可选对象存储及 Compose 变量传递 |
| [模块边界](docs/module-simplification.md) | Root、Skill、管理和协议模块职责 |

历史设计、开发交接与上游记录分别保存在 `docs/design/`、[HANDOFF.md](HANDOFF.md) 和 [UPSTREAM.md](UPSTREAM.md)。实际操作以当前配置文档及对应版本代码为准。

## 许可证

采用 Apache License 2.0，详见 [LICENSE](LICENSE)。
