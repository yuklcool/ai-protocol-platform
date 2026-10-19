# 自托管部署与运维说明

第一次安装按[完整中文配置流程](docs/configuration-guide.md)操作；镜像用户可直接阅读[版本化镜像部署](docs/selfhost-release-images.md)。

## 1. 默认部署组成

| 服务 | 默认端口 | 职责 |
| --- | --- | --- |
| `frontend` | 主机 `3456` → 容器 `8080` | 中文界面、对话/工作台、后端代理 |
| `backend` | `1956` | FastAPI、ADK、认证、租户与协议运行时 |
| `postgres` | 容器网络 `5432` | 配置、账号、Session、Memory、账本 |
| `mcp-sandbox` | 主机 `3457` → 容器 `8080` | 独立浏览器源的 MCP Apps 沙箱 |

默认不要求 Redis、MinIO、Keycloak、Firebase 或 GCP。自托管使用 `SELF_HOSTED_MODE=1`、`LOCAL_MODE=0`，开发身份替身不能用于对外服务。

## 2. 部署方式

发布镜像：从 [v1.1.1 Release](https://github.com/yuklcool/ai-protocol-platform/releases/tag/v1.1.1) 下载 `docker-compose.release.yml` 与 `default.env.selfhost.example`，将后者保存为 `.env`，编辑配置后执行：

```bash
docker compose -f docker-compose.release.yml config --quiet
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

发布镜像不需要源码，支持 `linux/amd64` 和 `linux/arm64`。

源码构建：

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
# 配置密钥、管理员、数据库、模型和浏览器源。
docker compose config --quiet
docker compose up -d --build
```

源码模板带前导点，与 Release 资产名不同。根 Makefile 未提供 `docker-up`、`docker-down` 或 `selfhost-smoke` 目标，使用本文的 Compose 命令和现有脚本。

## 3. 认证与账号

默认 `AUTH_BACKEND=local-jwt`。使用 `openssl rand -base64 48` 生成密钥，首次启动填写：

```env
JWT_SIGNING_KEY=替换为至少32字节的随机密钥
SELFHOST_ADMIN_EMAIL=admin@example.com
SELFHOST_ADMIN_PASSWORD=替换为至少12字符的密码
```

初始管理员仅在 `auth_users` 为空时创建。后续重启不覆盖现有密码或角色；修改环境变量不能重置旧密码，应在用户管理中操作。密码使用加盐 `scrypt` 哈希。

JWT 默认有效期 60 分钟，浏览器保存在 `sessionStorage`；关闭标签页后需重新登录，当前没有 refresh-token 流程。服务端从持久化账号重新确认租户/权限；敏感账号变更会撤销旧会话。签名密钥需稳定保存，轮换时可通过 `JWT_PREVIOUS_SIGNING_KEYS` 暂时兼容旧密钥。密钥缺失/过短或首次启动缺少管理员配置会明确失败。

OIDC 是可选企业身份适配，见[OIDC 接入](docs/selfhost-oidc.md)。Firebase 保留云端适配；`AUTH_BACKEND=stub` 仅用于开发。

## 4. 持久化与租户

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ARTIFACT_BACKEND=local
ADK_ARTIFACT_ROOT=/data/artifacts
```

PostgreSQL 保存结构化数据，`object-data` 卷保存文件字节和 Artifact。发布卷名为 `ai-protocol-platform-postgres-data` 与 `ai-protocol-platform-object-data`。已有部署必须核实实际挂载，避免切换 Compose 时连接新空卷。

Session 使用 ADK `DatabaseSessionService`，按可信租户分区存储 app namespace。Memory 按 tenant/app/UID 分区，支持持久化文本/关键词召回，`MEMORY_SEARCH_SCAN_LIMIT` 限制扫描量。文件下载经认证接口处理，不暴露本地磁盘路径。

稳定 `tenant_id` 是授权边界；邮箱域名仅为兼容映射。Session、文件、Skill、MCP、工具、模型、审计和额度均需要租户作用域。

## 5. 初始化与历史迁移

后端启动依次执行 SQL migration、持久化种子初始化、初始管理员创建和 Uvicorn。`scripts/apply_selfhost_migrations.py` 幂等执行 SQL，并记录在 `platform_schema_migrations`。

自动 SQL migration 不代表历史 ownership 或 Session/Memory namespace 已迁移。已有部署按[历史归属迁移](docs/tenant-ownership-migration.md)执行，并单独审核 namespace 搬迁；无归属旧历史不会作为租户请求的自动回退数据源。

## 6. 模型、Root 与交互

在模型管理注册 Provider、模型和默认映射，再到 `/agent` 选择模型、绑定 Skill/工具/MCP/知识。密钥引用使用 `${OPENAI_API_KEY}` 等后端环境引用。

交互表单需要同时开启 `a2uiEnabled`、`allowSurfaceContextWrites`、`allowActionTriggeredRuns`。普通聊天与表单操作共享 `/api/agent/stream` 和 Root 策略。

Root 额度管理需要租户额度、模型价格和 `budgetEnabled`。Root 开关启用后直接创建持久化租户执行器，即使 `BUDGET_ENFORCER=off` 也会执行；环境变量用于兼容旧 Skill/外部预算接口，详见[配置流程](docs/configuration-guide.md)。

## 7. 域名与反向代理

| 公共地址 | 上游 |
| --- | --- |
| `https://ai.example.com` | 同网络 `frontend:8080`，或主机 `127.0.0.1:3456` |
| `https://mcp.example.com` | 同网络 `mcp-sandbox:8080`，或主机 `127.0.0.1:3457` |

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
FRONTEND_PUBLIC_URL=https://ai.example.com
```

两者必须不同浏览器源。代理支持持续 SSE 响应，避免缓存、缓冲和过短超时。发布前端在启动时替换沙箱地址和认证模式；源码的语言、品牌等是构建参数，修改后需重建。发布镜像不会读取任意 `NEXT_PUBLIC_*` 运行时变量。

## 8. 环境变量传递

`.env` 用于 Compose 插值，未列入服务 `environment`/`env_file` 的变量不会自动进入容器。默认传递常用模型/OIDC 参数；自定义模型密钥、MCP 密钥或 S3 参数需用额外 Compose 文件显式传递，见[配置流程](docs/configuration-guide.md#10-可选配置与环境变量传递)。

## 9. 日常检查

```bash
docker compose -f docker-compose.release.yml ps
docker compose -f docker-compose.release.yml logs --tail=100 backend
curl -fsS http://localhost:1956/health
curl -fsS http://localhost:3456/api/health
curl -fsS http://localhost:3457/sandbox.html >/dev/null
```

源码部署省略 `-f docker-compose.release.yml`，源码目录可运行 `bash scripts/smoke-selfhost.sh`。健康检查不代替真实模型、工具、A2UI、刷新恢复和双租户验收，见[协议验收](docs/protocol-operation-acceptance.md)。

## 10. 备份、升级与回滚

备份 PostgreSQL 和文件/Artifact 卷，另行保护配置与签名密钥。先在真实数据副本验证恢复、迁移和回滚。需要一致恢复点时，先停止业务写入再备份数据库和对象卷。

镜像回退可恢复旧 `APP_VERSION` 后拉取启动；不兼容数据库迁移还需恢复匹配的数据与对象备份。ownership journal 回滚、Session/Memory namespace 回滚和整体恢复分别验收。

v1.1.1 已完成[发布镜像验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)和[同提交真实协议/租户验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)。目标部署的历史迁移与回滚仍见 [Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9)。

## 11. 本地源码开发

需要 Python `>=3.11,<3.14`、`uv`、Node.js 和 npm；Node 版本与 Dockerfile/CI 对齐。

```bash
cd backend
uv sync
cd ../frontend
npm ci
cd ..
# 在 backend/.env 仅填写开发所需的模型配置，示例见下文。
make dev-local
```

开发环境示例（写入 `backend/.env`，不要覆盖已有文件）：

```env
GEMINI_API_KEY=替换为实际开发密钥
GOOGLE_GENAI_USE_VERTEXAI=false
```

或者填写已注册 OpenAI 兼容模型所需的 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`PLATFORM_DEFAULT_MODEL`。不要把生产自托管模板整体复制到开发环境，它包含 PostgreSQL、生产认证和自托管选择器。`LOCAL_MODE=1` 使用开发替身，不等于持久化或生产认证验收。正式自托管使用 Compose。
