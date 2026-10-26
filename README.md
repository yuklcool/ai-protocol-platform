# AI Protocol Platform

基于 Google ADK 的开源智能体应用平台，将 **Root Agent、Skills、AG-UI、A2UI、MCP、MCP Apps 与 A2A** 接入统一运行链路，支持中文界面和私有化部署。

平台只有一个面向用户的 Root Agent。模型、工具、MCP、知识和交互行为由 Root Agent 统一配置；Skill 用于复用指令、参考资料和资源文件。登录后进入稳定工作台，选择开始任务、恢复会话或查找成果；智能体可以调用工具、生成交互表单，并在刷新后恢复会话和界面状态。

**界面设计：**全站浅色、淡紫与薄荷绿的分层玻璃工作台，规范见 [DESIGN.md](DESIGN.md)，可查看[交互式设计示意稿](outputs/glass-workspace-design.html)。逐页覆盖及尚未运行验证的边界见[界面检查清单](docs/design/ui-redesign-acceptance.md)。

**第一次使用请从[完整中文配置流程](docs/configuration-guide.md)开始。**手册说明部署、登录、模型与公共能力、个人设置、交互和升级清理的配置与验收。

## 功能与入口

| 能力 | 使用方式 |
| --- | --- |
| 统一智能体 | 在 `/agent` 配置模型、指令、能力绑定、权限与交互，在 `/chat/root-agent` 对话 |
| 工作台与历史 | `/workspace` 提供新任务和最近会话；`/sessions` 分页查找并回到原会话，搜索仅覆盖已加载记录 |
| 我的成果 | `/results` 选择可访问会话后查看持久化 A2UI 交互成果摘要，再回原对话；不是全量文件索引，不包含上传附件 |
| 可复用技能 | `/skills` 能力中心区分发现、个人启用与使用；Studio 开启时独立编辑指令、参考资料、资源文件和访问控制 |
| 模型接入 | 在 `/admin/model-providers` 按步骤添加模型服务、选择模型、测试并用于平台 Root |
| 交互式界面 | AG-UI 传递运行事件，A2UI 渲染表单、操作和状态更新 |
| MCP 与 MCP Apps | 服务管理、健康检查、能力发现、工具调用及独立源沙箱渲染 |
| 对话附件 | 在普通对话上传 TXT、Markdown、CSV、文本 PDF、DOCX、XLSX、PPTX；选择参与本轮分析，恢复会话附件状态 |
| 知识检索 | 上传并解析资料，在 Root Agent 中创建、绑定和检索知识来源 |
| 用户与个人配置 | 公共 Agent 能力、个人 Skill/信息与用户数据隔离 |
| 持久化与统计 | PostgreSQL 保存业务数据、会话、记忆和用量；持久卷保存文件与 Artifact |

对话附件的配置、格式范围、故障处理和验收要求见[文件上传与分析说明](docs/chat-file-analysis.md)。

照明场景的结构化结果、六场景交互、MCP 适配契约及生产接入边界见[照明查询接入说明](docs/lighting-query-integration.md)。

## 运行架构

| 层次 | 组件与职责 |
| --- | --- |
| 浏览器 | Next.js / React、统一对话与工作台、AG-UI 客户端、A2UI 渲染器 |
| 应用后端 | FastAPI、身份认证、用户授权、模型/MCP 管理和协议接口 |
| 智能体运行时 | Google ADK、Root Agent、Skill 指令加载、原生工具、MCP 和 A2A |
| 数据存储 | PostgreSQL：平台配置、用户账号、Session 和 Memory |
| 文件与沙箱 | 持久卷：文件和 Artifact；独立浏览器源：MCP Apps 沙箱 |

默认部署包含 `frontend`、`backend`、`postgres`、`mcp-sandbox` 四个服务，不要求 GCP、Firebase、Redis、MinIO 或 Keycloak。

## 快速部署

以下命令用于**全新安装**。已有部署先阅读[升级清理说明](docs/configuration-guide.md#7-旧部署升级)，保留现有配置和数据卷。

### 使用 v2.0.0 发布镜像

需要 Docker Engine、Compose v2，以及到 GHCR 和模型服务的网络连接。

```bash
mkdir -p ai-protocol-platform-deploy
cd ai-protocol-platform-deploy
release_version=v2.0.0
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/docker-compose.release.yml" -o docker-compose.release.yml
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/default.env.selfhost.example" -o .env
chmod 600 .env
openssl rand -base64 48
```

编辑 `.env`，至少完成下表；所有占位内容均应替换：

| 配置项 | 填写要求 |
| --- | --- |
| `APP_VERSION` | 确认为 `v2.0.0`，生产环境使用明确版本 |
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

以下流程对应当前源码；发布镜像以对应版本的发布说明为准。

1. **模型**：注册服务和模型，测试普通生成与工具调用，再应用到 Root Agent。
2. **用户**：创建账号，无需组织、权限组或模型白名单。
3. **公共能力**：在 Agent 中绑定公共 Skill、原生工具、MCP 和知识。
4. **个人配置**：用户绑定自己专有的 Skill，保存个人信息与偏好。
5. **交互与验收**：验证聊天、MCP、A2UI 操作、刷新恢复及跨用户拒绝。
6. **用量**：按用户和模型查看 Token 与估算费用。

逐字段示例和排错见[完整中文配置流程](docs/configuration-guide.md)。

## 地址、域名与接口

| 用途 | 默认地址或接口 |
| --- | --- |
| 前端 | `http://localhost:3456` |
| 工作台 / 历史 / 成果 | `/workspace` / `/sessions` / `/results` |
| Root 对话 | `/chat/root-agent` |
| 管理就绪与资源接入 | `/admin`（展示真实配置与模型测试记录，不代替目标账号验收） |
| 后端接口文档 | `http://localhost:1956/docs` |
| 后端健康检查 | `GET /health` |
| 统一 AG-UI 流 | `POST /api/agent/stream` |
| 兼容 Skill 流 | `POST /api/skill/{skill_id}/stream` |
| 当前身份 | `GET /api/auth/whoami` |
| MCP Apps 沙箱 | `http://localhost:3457/sandbox.html` |

远程部署应将前端和沙箱分别映射到两个浏览器源，例如 `https://ai.example.com` 与 `https://mcp.example.com`，并设置 `ALLOW_ORIGINS`、`MCP_SANDBOX_PUBLIC_URL`、`MCP_SANDBOX_ALLOWED_HOST_ORIGINS`。浏览器中的 `localhost` 不是远程服务器地址。

## 版本状态与升级边界

v2.0.0 使用“Agent 公共能力 + 用户个人 Skill 与信息”的配置模型。首次升级直接清理旧组织数据，不迁移或重新分配归属；账号凭据与公共平台配置保留。详见[升级清理说明](docs/configuration-guide.md#7-旧部署升级)。

[正式 Release](https://github.com/yuklcool/ai-protocol-platform/releases/tag/v2.0.0) 提供后端、前端和 MCP 沙箱镜像及固定版本的部署配置。发布由同提交的模型、浏览器、数据库、构建与安全检查控制。

当前 A2UI 支持范围为 **v0.9 + SDK basic catalog**；AG-UI 后端桥接锁定 `ag-ui-adk==0.6.5`、`google-adk==1.31.1`。知识检索为解析文本上的关键词检索，用量费用是估算值。

## 中文文档导航

| 文档 | 内容 |
| --- | --- |
| [完整配置流程](docs/configuration-guide.md) | 首次部署到业务可用的操作、参数解释与排错 |
| [自托管说明](SELFHOST.md) | 部署方式、认证、持久化和日常运维 |
| [版本化镜像部署](docs/selfhost-release-images.md) | 下载、版本、镜像来源、升级与回滚 |
| [模型接入](docs/selfhost-openai-compatible.md) | 地址、密钥引用、模型 ID、能力与价格 |
| [MCP 配置](docs/selfhost-mcp-server.md) | 注册、凭证、健康检查、发现、绑定和验证 |
| [Root 控制台](docs/root-console-completion.md) | 知识、账号、用户策略、预算和用量边界 |
| [协议验收](docs/protocol-operation-acceptance.md) | A2UI / AG-UI 操作验收 |
| [真实 Provider 验收](docs/real-provider-acceptance.md) | 真实模型和 A/B 用户工作流 |
| [OIDC 接入](docs/selfhost-oidc.md) | 企业认证与显式账号关联 |
| [OIDC 示例](docs/oidc-providers.md) | Keycloak、Entra ID 和 Okta |
| [S3 兼容存储](docs/s3-object-storage.md) | 可选对象存储及 Compose 变量传递 |
| [模块边界](docs/module-simplification.md) | Root、Skill、管理和协议模块职责 |

当前设计从[设计索引](docs/design/README.md)进入；历史版本已移至[设计归档](docs/archive/design/README.md)。开发交接与上游记录见 [HANDOFF.md](HANDOFF.md) 和 [UPSTREAM.md](UPSTREAM.md)。实际操作以当前配置文档及对应版本代码为准。

## 许可证

采用 Apache License 2.0，详见 [LICENSE](LICENSE)。
