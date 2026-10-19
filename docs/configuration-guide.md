# 完整中文配置流程

本文对应当前 main 源码中的自托管部署及 Root Agent 控制台，从服务器准备到聊天、工具、MCP Apps、A2UI 和租户隔离逐步配置。

权限组改版需要包含本次改动的后端与前端同时部署。已发布的 v1.1.1 镜像不能直接视为包含这些改动；测试当前源码请使用源码 Compose。既有部署仍需完成第 12 节的目标环境迁移和回滚验收。

命令使用 Linux / Bash。域名、邮箱、密钥和模型名称均为示例，需替换。已有部署先看第 12 节，不要覆盖旧 `.env`、重新初始化数据库或删除数据卷。

## 1. 配置顺序与完成标准

| 顺序 | 配置 | 完成标准 |
| --- | --- | --- |
| 1 | 服务、数据库、认证、浏览器源 | 四个服务健康，管理员可登录 |
| 2 | Provider、模型、路由、价格 | 普通生成与工具调用探测通过 |
| 3 | 租户、账号、模型与权限策略 | 登录归属及权限预览正确 |
| 4 | Skill、工具规则、MCP | 资源可发现且授权明确 |
| 5 | Root 模型与能力绑定 | 普通对话实际调用授权能力 |
| 6 | 知识与 A2UI | 检索有来源，表单可操作并刷新恢复 |
| 7 | Root 预算、租户额度与价格 | 真实调用有记录，超额不影响其他租户 |
| 8 | 备份与验收 | 重启可恢复，隔离与异常终态正确 |

## 2. 准备服务器和安装文件

需要 Docker Engine、Compose v2，以及到 GitHub/GHCR 和模型服务的网络。默认只需 PostgreSQL 和对象卷，不必安装 Redis、MinIO 或 Keycloak。

```bash
docker --version
docker compose version
mkdir -p ai-protocol-platform-deploy
cd ai-protocol-platform-deploy
release_version=v1.1.1
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/docker-compose.release.yml" -o docker-compose.release.yml
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/default.env.selfhost.example" -o .env
chmod 600 .env
```

这组命令只用于全新目录。升级时将模板另存为 `.env.new`，比较差异后保留旧值。下载失败先确认网络、版本和资产名，不要把错误页面作为配置。

## 3. 配置部署环境

### 3.1 必填项

运行 `openssl rand -base64 48` 生成 JWT 密钥，编辑 `.env`：

```env
APP_VERSION=v1.1.1
SELF_HOSTED_MODE=1
LOCAL_MODE=0
AUTH_BACKEND=local-jwt
JWT_SIGNING_KEY=替换为生成的随机密钥
SELFHOST_ADMIN_EMAIL=admin@example.com
SELFHOST_ADMIN_PASSWORD=替换为至少12字符的管理员密码
POSTGRES_DB=aip
POSTGRES_USER=aip
POSTGRES_PASSWORD=替换为数据库密码
DATABASE_URL=postgresql://aip:替换为数据库密码@postgres:5432/aip
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ARTIFACT_BACKEND=local
ADK_ARTIFACT_ROOT=/data/artifacts
OPENAI_API_KEY=替换为实际模型密钥
```

连接串用户名、密码、数据库名与 `POSTGRES_*` 一致。密码中的 `@`、`:`、`/`、`#` 等 URI 保留字符需在连接串中编码；也可生成随机十六进制密码简化操作。已有 PostgreSQL 卷不会因修改 `POSTGRES_PASSWORD` 自动更新数据库内密码。

先保留模板内已注册的默认模型作为启动值，登录后按第 5 节注册自己的模型。API Key 不会自动创建自定义模型项。

### 3.2 浏览器访问地址

同机本地访问：

```env
MCP_SANDBOX_PUBLIC_URL=http://localhost:3457
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=http://localhost:3456
ALLOW_ORIGINS=http://localhost:3456
FRONTEND_PUBLIC_URL=http://localhost:3456
```

其他电脑访问服务器时，改为浏览器可达的地址。互联网部署使用 HTTPS 和两个不同源：

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
FRONTEND_PUBLIC_URL=https://ai.example.com
```

源地址包含正确协议、主机和端口，白名单不填页面路径。模型/MCP 后端地址则需从 backend 容器可达；容器内 `localhost` 指向该容器自身。

## 4. 启动、登录和配置入口

```bash
docker compose -f docker-compose.release.yml config --quiet
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
docker compose -f docker-compose.release.yml ps
docker compose -f docker-compose.release.yml logs --tail=100 backend
```

打开前端，以初始管理员登录。账号仅在本地用户库为空时创建，后续修改初始环境变量不会覆盖旧密码。

| 页面 | 路径 | 配置权限 |
| --- | --- | --- |
| 管理总览 | `/admin` | 按角色显示入口 |
| 模型 | `/admin/model-providers` | 平台管理员 |
| 租户、租户 Agent 策略 | `/admin/tenants` | 按平台/租户管理范围操作 |
| 用户、分组 | `/admin/users`、`/admin/groups` | 按身份源和管理权限操作 |
| MCP 服务 | `/admin/mcp-servers` | 按平台/租户作用域操作 |
| Root Agent | `/agent` | 平台管理员管理 Root 设置 |
| Skill | `/skills` | 有资源权限的用户 |
| 用量与运行分析 | `/admin/analytics` | 按授权范围查看 |
| 管理审计 | `/admin/audit` | 按授权范围查看 |
| 普通对话 | `/chat/root-agent` | 有相应权限的已认证用户 |

## 5. 注册 Provider 和模型

### 5.1 准备服务信息

确认 API Base URL、API Key、模型 API 名称及流式工具调用支持。Base URL 通常包含 `/v1`，不要填完整 `/chat/completions` 地址。

动态 OpenAI 兼容服务可在 `.env` 填写 `OPENAI_API_KEY`，再应用环境变更：

```bash
docker compose -f docker-compose.release.yml up -d backend
```

`restart` 不加载新容器环境；使用 `up -d` 应用配置变化。自定义变量见第 10 节。

### 5.2 创建 Provider

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| Provider ID | `my-gateway` | 稳定内部标识 |
| 名称 | `我的模型网关` | 展示名称 |
| Base URL | `https://model.example.com/v1` | backend 可达的 API 前缀 |
| 密钥引用 | `${OPENAI_API_KEY}` | 原样填写引用，不填明文 Key |
| 启用 | 开启 | 禁用后不可作为可用 Provider |

在“模型”保存 Provider 并执行连通性检查。动态表单当前类型为 `openai-compatible`；Gemini/Anthropic 原生 API 走已有注册表与各自凭证，不要填入不兼容的原生 endpoint。

### 5.3 创建模型

| 字段 | 填写方式 |
| --- | --- |
| 模型 ID | 如 `gateway-chat`，供平台引用 |
| API 模型名 | 服务实际暴露的名称，逐字匹配 |
| Provider | 选择 `my-gateway` |
| 层级 | 按需要选择 `default`、`smart`、`fast` |
| 上下文、最大输出 | 按模型/网关实际限制填写 |
| 支持工具调用 | 工具/MCP/A2UI 需要开启且实测通过 |
| 推理参数 | 仅在服务明确支持时开启 |
| Responses API | 仅在实现并验证后开启；普通兼容服务先关闭 |
| 输入/输出价格 | 同时填写美元/百万 Token 价格，或同时留空 |
| 启用 | 开启 |

模型 ID 与 API 名称可以不同。Root 选择 `gateway-chat`，远端收到对应 `api_name`。价格用于估算成本，有上限租户使用未计价模型会在调用前被拒绝。

### 5.4 探测与路由

分别执行普通生成与工具调用探测。通过后保存平台默认模型及 `default`、`smart`、`fast` 映射；单模型可全部指向 `gateway-chat`。

到 `/agent` 模型设置选择该模型并保存。租户白名单也需包含该模型，平台可用不等于该租户可用。

## 6. 租户、账号与权限

### 6.1 创建租户并设置允许资源

在 `/admin/tenants` 新建稳定租户，例如 `tenant-a`，保存名称和可选身份域。身份域仅用于登录身份映射，租户 ID 是独立的主键。存储命名空间不会自动搬迁历史数据。

保存租户后，选择“租户允许的 Skills”和“租户允许的 MCP 服务器”。空列表表示不允许。模型白名单、默认模型和额度由平台管理员设置，租户管理员不能提高或清空限制。

### 6.2 配置当前租户 Root

在 `/agent` 绑定平台通用能力，或在租户页设置租户 Root 覆盖。租户覆盖中的列表会**替换**平台列表，未设置的字段继承平台配置，显式空列表表示不绑定。租户私有 Skill/MCP 可以直接放入该租户覆盖，无需写入全局 Root。

原生工具由当前 Root 直接绑定。额外 Skills 和 MCP 还必须同时通过租户白名单、权限组和资源自身的租户/ACL 检查。默认拒绝是固定行为，无需开启 `failClosed`。

### 6.3 创建权限组并分配用户

1. 打开 `/admin/groups`，选择租户、填写组名。
2. 勾选需要的 Skills 和 MCP。这里只显示当前 Root 与租户同时允许的资源；如果为空，先完成前两步配置。
3. 选择“普通成员”或“租户管理员”。只有平台管理员可以创建、调整和分配租户管理员组，权限组不能授予平台超级管理员。
4. 打开 `/admin/users`，创建本地账号、选择租户，再勾选一个或多个同租户权限组。OIDC 模式只管理已关联账号的授权，登录身份与密码在身份源维护；账号需显式关联 `issuer + sub`，见[OIDC 接入](selfhost-oidc.md)。
5. 点击用户行的“有效权限”，确认后端返回的可用 Skills/MCP，然后登录该用户进行实际对话验证。

有效 Skills = 当前租户 Root Skills ∩ 租户允许 Skills ∩ 用户所有权限组 Skills 的并集，随后检查资源 ACL。MCP 使用相同的交集，并检查服务器启用状态与租户归属。未分配组或组未授权时，普通用户不能使用额外 Skills/MCP；Root 绑定本身不等于向所有用户授权。

成员关系和组资源授权逐请求读取。撤销成员、删除组、Root 解绑或服务器停用后，后续请求应立即拒绝。停用账号、改变租户或重置密码会撤销已有令牌。平台超级管理员为受保护账号，不能通过普通账号编辑或组授权变更。

旧 `groupTags` 手动授予/撤销、派生标签、单独的工具权限管理页、Skill 中的 MCP 绑定均不再作为当前 Root 授权流程使用。既有安装升级时，应先备份配置与数据，再显式建立权限组和成员关系；不会自动把旧标签、通配规则转换为新授权。

## 7. Skill、原生工具与 MCP

### 7.1 Skill 与工具

使用目标租户账号在 `/skills` 创建名称、描述、指令、参考资料、资源文件和访问控制，或选择平台通用模板，然后到对应 Root 的“技能”绑定。跨租户私有 Skill 不能通过组授权共享；同租户多人使用时也需在 Skill 自身访问控制中允许这些用户。Skill 是能力内容，不会成为第二个 Agent 或自行扩大工具权限。

Root 的“工具”勾选需要的原生工具并保存。到 `/chat/root-agent` 用具体任务验证技能加载和工具执行。

### 7.2 MCP 服务

| 字段 | 填写方式 |
| --- | --- |
| 服务 ID | 例如 `business-mcp` |
| URL | backend 可达的 endpoint，如 `https://tools.example.com/mcp` |
| 传输 | 按服务契约选择 Streamable HTTP、SSE 等支持方式 |
| 作用域 | 私有集成选 Tenant，明确共享才选 Platform |
| 凭证 | 按服务要求设置请求头，优先环境引用 |
| 启用 | 开启 |

保存后执行“健康检查”，确认真实 MCP `initialize`，再“发现”工具、资源、提示词。保存成功不等于协议可用。

在当前 Root 绑定 MCP 服务，在租户允许资源中勾选，再通过权限组分配给用户。保存后从普通对话发起真实任务。返回 MCP Apps 资源时应通过平台代理和独立源沙箱渲染；发现 `ui://` 不能代替模型实际调用。

编辑凭证留空保留旧请求头，明确选择清除才删除。`${MCP_TOKEN}` 必须已进入 backend 环境。详见[MCP 配置](selfhost-mcp-server.md)。

## 8. 知识与交互式界面

### 8.1 知识来源

在 Root“知识”上传资料，等待 `parsed`，选择文档，设“仅我可用”或“同租户成员可检索”，创建来源、选中并保存 Root。

预览读取已保存配置。用独有关键词确认来源、摘录和位置，再用普通对话验证引用。撤销共享/删除来源后应立即无法检索。当前是关键词检索，每来源最多扫描前 200 万字符，不保证语义向量检索或图片 OCR。

### 8.2 对话文件上传与分析

打开普通 Root 对话，使用输入框旁的“添加文件或拖入此处”，等待“可用于分析”，检查勾选标签后发送问题。默认本地解析支持 TXT、Markdown、CSV、文本 PDF、DOCX、XLSX、PPTX，单文件最多 25 MiB、每会话最多 10 个；无需 AILANG 或 GCP。图片与扫描 PDF 不做 OCR。

取消勾选控制下一轮是否读取，移除标签不删除原文件。后端保存打开顺序和勾选状态，附件加载/保存/解析期间禁止发送，失败可重试。详见[完整文件分析说明](chat-file-analysis.md)，其中区分解析成功、模型输入契约、真实模型分析和目标安装迁移验收。这些是对应源码修改的行为，使用发布镜像时先确认该版本包含修改。

### 8.3 A2UI / AG-UI 交互

在 Root“交互”配置：

| 字段 | 作用 |
| --- | --- |
| `a2uiEnabled` | 开启 A2UI 输出 |
| `allowSurfaceContextWrites` | 允许表单输入/上下文写入 |
| `allowActionTriggeredRuns` | 点击操作继续触发 Root 运行 |
| `defaultSurface` | 支持的承载位置，默认 `chat` |
| `defaultUpdateMode` | `replace` 或 `patch`；表单仍需正确生命周期消息 |
| `voiceEnabled` | 可选朗读，默认浏览器语音 |

前三项需同时启用。保存后让模型生成带输入框和按钮的简单表单，输入并提交，确认运行与界面更新；刷新确认输入/结果恢复，再提交一次，最后继续普通聊天。

支持 A2UI v0.9 和 SDK basic catalog，后端桥接锁定 `ag-ui-adk==0.6.5`、`google-adk==1.31.1`。其他版本或任意组件目录不自动兼容。

## 9. 额度与用量

Root 额度控制必须配置以下三项：

1. 平台管理员为租户设置正的 `llmBudgetUsd`、`llmBudgetPeriod`（`daily`/`weekly`/`monthly`）和 `llmBudgetSoftThreshold`。
2. 模型有有效的输入/输出价格。
3. Root“租户额度”或相应租户覆盖中启用 `budgetEnabled` 并保存。

Root 开关启用后，运行时会直接使用 `TenantRepositoryBudgetEnforcer`，不依赖 `BUDGET_ENFORCER` 的值。该环境变量可选设为 `tenant-repository`，用于旧 Skill/外部预算接口；变更环境需用 `up -d backend` 应用。它本身不能代替 Root 开关。

`llmBudgetUsd=0` 表示不限额。只填额度、只注册执行器或只配置旧 Skill 预算不能替代 Root 完整配置。

在“用量与运行分析”查看 Token、调用数、估算成本、已计费与预留。统计不回填历史，不存储对话正文；Provider 未返回用量的调用不计入统计。

使用测试租户 A/B 分别真实调用工具并产生正用量，将 A 额度调整到低于已消费值，确认下一次**不带 Skill/capability hint 的普通聊天**返回 `BUDGET_EXCEEDED`，B 仍可调用自己的工具。

## 10. 可选配置与环境变量传递

### 10.1 自定义密钥

`.env` 不是自动注入所有容器的文件。新增 `MODEL_GATEWAY_KEY`、`MCP_TOKEN` 时，填入 `.env`，并创建 `docker-compose.extra.yml`：

```yaml
services:
  backend:
    environment:
      MODEL_GATEWAY_KEY: "${MODEL_GATEWAY_KEY:?请在.env中填写模型密钥}"
      MCP_TOKEN: "${MCP_TOKEN:?请在.env中填写MCP密钥}"
```

```bash
docker compose -f docker-compose.release.yml -f docker-compose.extra.yml config --quiet
docker compose -f docker-compose.release.yml -f docker-compose.extra.yml up -d
```

Provider 密钥引用填 `${MODEL_GATEWAY_KEY}`。MCP 请求头可填 `Authorization=${MCP_TOKEN}`；若要求 Bearer，变量值或请求头表达式需包含服务要求的 `Bearer ` 前缀。后续管理始终使用相同两个 `-f` 文件。真实密钥不提交 Git/Issue。

### 10.2 中文与品牌

默认简体中文，界面可切换语言。源码通过 `DEFAULT_LOCALE`、`APP_NAME`、`APP_TAGLINE`、`APP_DESCRIPTION`、Logo 和主题变量修改后重建前端。预构建 v1.1.1 仅替换已实现的运行时参数（认证模式、沙箱 URL）；换品牌需自建镜像。

### 10.3 身份与存储

企业登录见[OIDC](selfhost-oidc.md)和[提供商示例](oidc-providers.md)。S3 见[存储配置](s3-object-storage.md)，需要显式传递变量；切换适配不会自动搬迁文件，Artifact 独立配置。

### 10.4 反向代理

两个 HTTPS 虚拟主机分别代理前端和沙箱。主机代理使用 `127.0.0.1:3456`/`3457`；同 Docker 网络使用 `frontend:8080`/`mcp-sandbox:8080`。AG-UI 需持续流式响应，关闭缓存/响应缓冲，设置足够的读取超时。

## 11. 完成验收

| 项目 | 观察结果 |
| --- | --- |
| 健康与身份 | 服务健康，登录和 `/api/auth/whoami` 身份正确 |
| 模型 | 普通生成、流式工具调用通过，无静默切换 Provider |
| Root | 模型/绑定保存后仍存在，实际工具成功 |
| 知识 | 检索有来源，撤权立即生效 |
| 对话附件 | 新会话与恢复会话可上传、解析、选择、取消选择和下载；真实 Provider 读取独有内容并正确计算和引用；刷新/重建后状态存在，失败不报告成功 |
| MCP Apps | 调用后渲染，禁用后不可继续使用 |
| A2UI | 生成、输入、提交、更新、刷新、再次提交通过 |
| 异常与取消 | 失败/截断显示错误，取消后可再次操作，不误报成功 |
| 持久化 | backend 重建后会话、记忆、文件和界面仍可用 |
| 租户 | 相同 UID 不同租户的 Session、Memory、文件、工具、模型、审计隔离 |
| 额度 | A 超额在模型/工具调用前阻断，B 可用，账本独立 |
| 恢复 | 备份在隔离环境恢复成功 |

源码可用 `bash scripts/smoke-selfhost.sh` 检查基础服务，不代替业务验收。工作流与证据要求见[协议验收](protocol-operation-acceptance.md)及[真实 Provider 验收](real-provider-acceptance.md)。

## 12. 已有部署升级迁移与回滚

### 12.1 升级前

记录旧版本/镜像 digest、实际卷、配置及租户数据数量。停止写入或取得一致快照，备份 PostgreSQL、`/data/objects`、`/data/artifacts`，另行保护 JWT 和环境配置。在隔离副本恢复并确认旧版本可用。

默认本地存储的维护窗口备份示例（额外 Compose 文件需要一并传入，其他写入者也应暂停）：

```bash
backup_dir="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
docker compose -f docker-compose.release.yml stop backend
docker compose -f docker-compose.release.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$backup_dir/postgres.dump"
docker compose -f docker-compose.release.yml run --rm --no-deps -T \
  --entrypoint sh backend -c 'tar -C /data -czf - objects artifacts' \
  > "$backup_dir/object-data.tgz"
cp .env "$backup_dir/environment.env"
cp docker-compose.release.yml "$backup_dir/docker-compose.release.yml"
chmod 600 "$backup_dir"/*
docker compose -f docker-compose.release.yml up -d backend
```

逐条确认退出状态，失败的转储不能作为有效备份；额外 Compose 文件和外部对象存储也需备份。恢复演练在隔离数据库/对象卷进行，使用 `pg_restore` 恢复转储、解包对应对象数据，再验证旧版本的账号、会话、文件和记忆。默认 Compose 使用固定卷/网络名，隔离副本必须修改卷名、网络名与端口，不能在同一主机直接复用生产配置。

新模板另存，合并新增键而不覆盖 `.env`，确认所有 Compose 文件、身份映射和存储配置一致。

### 12.2 三类迁移分别审核

| 层次 | 处理 |
| --- | --- |
| SQL schema | 后端幂等执行，检查 `platform_schema_migrations` 和日志 |
| metadata ownership | `migrate_tenants.py` dry-run、人工复核、apply/verify，保存 run id |
| ADK Session/Memory namespace | 按权威 Session 索引及 tenant ownership 单独设计、审核、迁移、验证、回滚 |

metadata 工具不替代 namespace 搬迁，无归属旧历史不会自动搜索。命令见[迁移手册](tenant-ownership-migration.md)。

### 12.3 回滚和放行

真实数据副本中演练 journal 回滚、namespace 撤销和整体恢复。journal 遇到业务修改导致的 drift 会拒绝覆盖，不应绕过。镜像回退不自动撤销不兼容数据库变更。

演练通过后，在目标维护窗口 apply/verify，完成第 11 节复验，再恢复写入。保留映射、run id、digest、验收和恢复记录。

v1.1.1 [镜像发布](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)与[同提交协议实跑](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)已成功；[Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 仍保留目标部署历史迁移与回滚验收。

## 13. 常见问题

| 现象 | 优先检查 |
| --- | --- |
| backend 不启动 | JWT 长度、初始管理员、数据库连接和 migration 日志 |
| 改初始密码仍不能登录 | 初始变量不重置已有账号，核查旧账号或管理端重置 |
| Provider 保存失败 | 引用是否为 `${ENV_VAR}`，是否误填明文 Key |
| 密钥引用无法解析 | 变量是否传入 backend，是否仅修改后执行了 `restart` |
| 探测成功但聊天失败 | Root 保存、租户白名单、默认映射和预算价格 |
| 文字正常工具失败 | 流式工具能力、开关、Root 绑定、租户允许资源与权限组 |
| MCP 健康失败 | 容器网络、endpoint、传输、认证头和启用状态 |
| MCP App 空白 | 沙箱公共 URL、前端白名单、独立源、TLS 和代理 |
| 表单按钮无效 | 上下文/操作触发开关、当前 Session 和流式错误 |
| 额度不拦截 | 正额度、价格和 Root 预算开关；旧 Skill 另查其执行器/预算配置 |
| 用量缺少旧记录 | 不回填历史，核查 Provider 用量返回与租户/时间范围 |
| 升级后旧历史不可见 | 卷挂载和 namespace 迁移，不能关闭隔离或猜归属 |
| 品牌不生效 | 源码前端需重建，发布镜像不任意运行时换品牌 |

排查时先看最近容器日志，分享前去除凭证和个人数据。部署方式见[自托管说明](../SELFHOST.md)。
