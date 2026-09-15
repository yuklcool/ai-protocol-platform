# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：2026-09-15
> 当前阶段：**#4～#8 已完成；当前主线为 #9 多租户隔离，正在完成 MCP Proxy / seed / CI 收口。**

---

## 1. 当前结论

旧版 HANDOFF（2026-09-13）中“核心改造尚未开始”的判断已经失效。当前 `main` 已完成多轮 Self-host 核心改造，并有真实 PostgreSQL / Docker image CI 验证。

现在项目不再是“只有 Roadmap 的 fork”，而是已经具备以下自托管底座：

- PostgreSQL Repository / persistence abstraction
- PostgreSQL ADK Session
- PostgreSQL durable Memory
- PostgreSQL 下 A2UI surface / clientDataModel / lastAction 恢复
- Local ObjectStorage + Docker Volume
- ADK FileArtifactService 本地持久化
- Docker Compose：frontend / backend / postgres / mcp-sandbox
- provider-driven OpenAI-compatible model routing
- Self-host CI 与 persistence regression CI

当前 #7 内置 JWT 与 #8 无 GCP Self-host 已完成并关闭。接下来按顺序推进：

1. #9 多租户：完成 MCP Proxy / seed / CI；继续 Audit tenant attribution 与 quota enforcement。
2. #1/#2/#3 最终真实协议验收与 Issue 收口（不可把单测替代浏览器验收）。
3. #10/#11 模型与 MCP 管理产品化。


---

## 2. 平台架构仍然保持

```text
Web Frontend (Next.js / React)
        │
        │ AG-UI
        ▼
FastAPI Backend
        │
        ▼
Google ADK Agent Runtime
        │
        ├── Runtime Skills / SKILL.md
        ├── Native Tools
        ├── MCP
        ├── MCP Apps
        ├── A2UI
        └── A2A
```

核心标准链路没有因为 Self-host 改造而被替换。

必须继续遵守：

- 不自造 A2UI 协议
- 不破坏 AG-UI event 路径
- MCP Apps 继续独立 sandbox/origin
- Google Cloud 能力改成 adapter/provider，不直接删除
- 上游兼容优先通过扩展层完成

---

## 3. 当前 Self-host 默认架构

实际默认栈已经是：

```text
Browser
   ↓
Frontend :3456
   ↓
Backend :1956
   ├── Google ADK
   ├── Runtime Skills
   ├── MCP / MCP Apps
   ├── AG-UI / A2UI
   │
   ├── PostgreSQL :5432
   │    ├── platform/domain data
   │    ├── ADK Session + events/state
   │    └── durable Memory
   │
   └── /data
        ├── objects
        └── artifacts

MCP Apps sandbox :3457
```

默认不需要：

- Redis
- MinIO
- Keycloak
- 独立 Session DB
- 独立 Memory DB
- 独立消息队列
- 独立向量数据库

---

## 4. Issue 状态（以代码/CI 为准）

### Phase 0 / 1

#### #1 LOCAL_MODE 全链路基线 — 进行中

已经有 `scripts/smoke-selfhost.sh`、Self-host CI 和大量 persistence/protocol regression。

仍需最终人工/真实协议验收：

- 普通 Chat
- Runtime Skill
- MCP Tool
- MCP App iframe
- Workspace Demo / A2UI surface
- A2UI action round-trip

因此 #1 暂不关闭。

#### #2 通用 OpenAI-compatible — 主体已实现，待收口

`backend/adk/agent.py::resolve_model()` 已改为 registry/provider-driven，而不是依赖模型名前缀决定 provider。

当前支持：

```text
provider: google
provider: anthropic
provider: openai
```

OpenAI-compatible 路径支持：

```text
OPENAI_API_KEY
OPENAI_API_BASE
api_name: arbitrary model name
supports_reasoning
supports_responses_api
```

因此 DeepSeek / Qwen / vLLM / LiteLLM Proxy / OneAPI / NewAPI / 内部 OpenAI-compatible gateway 都可以通过 registry 配置进入同一 provider 路径。

Issue 仍开着的原因是需要把最终回归/真实 Tool Calling 验收记录补齐，而不是重新开发路由。

#### #3 Docker Compose — 主体已实现，待收口

根目录已有 `docker-compose.yml`：

- PostgreSQL 16
- backend
- frontend
- MCP sandbox
- healthcheck
- restart policy
- persistent volumes
- service dependency
- OpenAI-compatible env

Self-host CI 已经实际 build image 并测试 PostgreSQL / Session / Memory / A2UI / ObjectStorage。

剩余：

- `make docker-up` / `make docker-down`
- 真实 Chat / Skill / MCP / MCP App / A2UI 协议验收

---

## 5. #4 PostgreSQL Persistence — 已完成

#4 已最终验收关闭。

当前结构：

```text
Business code
      ↓
Repository
 ├── PostgreSQL   ← Self-host 默认
 ├── Firestore    ← GCP 兼容
 └── Memory       ← dev/test
```

关键能力：

- `DATA_BACKEND=memory|firestore|postgres`
- `PostgresRepository`
- `FirestoreRepository`
- `MemoryRepository`
- migration CLI
- `TenantRepository`
- tenant-aware fail-closed guard
- PostgreSQL real integration CI
- runtime direct-Firestore import audit

核心业务运行时已迁移到 Repository 边界；CI 会阻止重新引入 `db.firestore` / `google.cloud.firestore` 直接依赖。

保留的 Firestore/GCP 边界是明确兼容层，而不是 Self-host 主路径依赖。

---

## 6. #5 Session / Memory / A2UI 恢复 — 已完成

Self-host 默认：

```env
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
```

Session：

- 直接复用 Google ADK 1.31.1 `DatabaseSessionService`
- 不维护第二套 Session SQL schema

Memory：

- 新增 `PostgresMemoryService`
- 使用现有 PostgreSQL Repository
- 不依赖 Redis
- 支持 durable ADK event memory
- 支持中文 substring/text recall

A2UI 恢复：

- `a2ui_surface:*` replay payload 落 Session state
- 历史接口返回 `a2ui_surfaces`
- 前端恢复 `SurfaceRegistry`
- `clientDataModel` 持久化并恢复
- `a2ui_surface_context.{surfaceId}.lastAction` 持久化
- backend 重建后 model-facing context 仍可恢复

真实 PostgreSQL CI 已验证跨 `DatabaseSessionService` 重建恢复。

---

## 7. #6 ObjectStorage / Artifact — 已完成

Self-host 默认：

```env
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ADK_ARTIFACT_ROOT=/data/artifacts
```

结构：

```text
/data
├── objects
│   └── tenants/...
└── artifacts
```

实现：

- 统一 `ObjectStorage` contract
- LocalStorage 默认
- GCS adapter 保留
- 文档 metadata 走 Repository/PostgreSQL
- binary 走 ObjectStorage
- stream upload/download
- tenant namespace
- preview/download 受控 API
- path traversal / symlink escape 测试
- recoverable delete state
- ADK official `FileArtifactService`
- Docker Volume 持久化

S3-compatible 已拆为 #16，可选，不阻塞默认架构，也不自动引入 MinIO。

---

## 8. #7 Built-in JWT — 已完成并关闭

- PostgreSQL 本地账号、scrypt 密码哈希、JWT 签发/验证与 key rotation。
- 首管理员 bootstrap；权限和租户来自服务端账号记录。
- 统一 User / AccessContext，Firebase 作为可选 provider。
- 前端邮箱密码登录、sessionStorage、whoami、过期/401 清理。
- REST / AG-UI Bearer token 链路已接入。
- OIDC / Keycloak 拆为可选 #17，不是默认部署依赖。

## 9. #8 GCP optionalization — 已完成并关闭

正式部署使用 `SELF_HOSTED_MODE=1`、`LOCAL_MODE=0`、`AUTH_BACKEND=local-jwt`。
无需 ADC、GCP project、Firebase、Vertex、GCS 即可启动；GCP adapter 保留为可选能力。

- `config/capabilities.py` 与 `/api/capabilities` 统一能力状态。
- `PLATFORM_DEFAULT_MODEL` 支持 OpenAI-compatible 根 Agent。
- AG-UI deployment App 按绝对文件路径加载，避免 `app` 同名模块冲突。
- Self-host no-GCP gate Run 34914798342 成功；该历史验收包含登录、启动、
  OpenAI-compatible、MCP、Chat/Skill/AG-UI、PostgreSQL 与 A2UI resume。
- ADK 传递依赖仍可能安装 GCP SDK；“无 GCP”指无配置、凭证、资源的运行依赖。

## 10. 当前主线：#9 显式 Tenant / 隔离 — OPEN

已在此前 main 落地：

- 显式 Tenant directory、domain mapping、迁移工具及稳定 tenant identity。
- Tenant-aware Repository、AccessContext 与管理员 scope。
- Session / Skill、Document / Folder / ObjectStorage 的 tenant 边界。
- Artifact 同时隔离 app_name 和 artifact-only user_id，弥补 ADK FileArtifactService
  不按 app_name 隔离磁盘路径的行为；不改 Session/Memory 的用户身份。
- observability enricher 不得覆盖认证后的 tenant.id。
- MCP registry 使用 `(tenant_id, server_id)` 缓存，并应用显式 scope policy。

本轮改造：

- HTTP MCP Proxy 在 POST / GET / DELETE 转发前，使用已认证 User 派生 tenant，
  检查配置 scope；跨租户/无 scope/未知 scope 均 404，缺失 tenant context 为 403。
- `scope=platform` 表示显式平台共享，仍须通过 Skill allowlist；
  `scope=tenant + tenantId` 仅允许该稳定租户。
- 内置 ext-apps / Toolbox / Maps Grounding seed 显式标记 `scope=platform`。
  ext-apps 无 URL 参数重种时保留已部署 URL、headers 及已声明的私有 scope。
- 历史无 scope 的自定义配置默认拒绝访问，需管理员明确迁移为平台共享或租户私有；
  不可批量将未知配置升级为共享。
- MCP registry、Proxy 与 seed 回归加入 Tenant isolation gate；修正先前 registry
  回归对 ADK connection params 属性的错误断言。

本轮本地验证：按更新后的 Tenant isolation gate 测试清单执行，**279 passed, 2 skipped**。
使用 SELF_HOSTED_MODE=1 / LOCAL_MODE=0 / local-jwt，数据与 Session/Memory 为 memory
测试后端；这不是本轮 Docker/PostgreSQL 或真实浏览器验收结果。

剩余工作（不得关闭 #9）：

1. Audit 增加显式 tenant attribution，并按稳定 tenant scope 读取；当前仍从 target
   推断 domain，不能据此宣称审计隔离完成。
2. quota/budget 的运行时 enforcement；TenantConfig 的 quota 字段不等于配额已执行。
3. 多租户端到端与旧数据迁移验收，再更新 #9 checklist 并决定是否关闭。

后续顺序：#9 → #1/#2/#3 验收收口 → #10/#11 → #12 中文化 → #13 Release。
#14 upstream sync 贯穿全程；#16 S3 与 #17 OIDC 为可选扩展。

---

## 11. 自托管启动

```bash
cp .env.selfhost.example .env
# 配置 JWT_SIGNING_KEY、首次管理员账号密码，以及至少一个 LLM provider

docker compose up -d --build
```

默认 persistence：

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
OBJECT_STORAGE_BACKEND=local
```

正式 Self-host 默认使用 local-jwt；LOCAL_MODE/stub 仅用于开发。具体管理员初始化及模型配置参见 SELFHOST.md。

---

## 12. 验证边界

当前 CI 已经覆盖：

- Repository Memory/PostgreSQL regression
- runtime Firestore direct-import audit
- tenant-aware PostgreSQL acceptance
- Session 重建恢复
- Memory 重建恢复
- A2UI state reconstruction
- local ObjectStorage / Artifact container reconstruction
- document lifecycle / tenant checks / streaming
- backend/frontend image build（Self-host workflow）

发布前仍需保留真实协议人工验收：

1. normal Chat
2. Runtime Skill
3. MCP Tool
4. MCP App sandbox
5. A2UI surface
6. A2UI action round-trip

不要把 unit/integration 通过等同于完整浏览器协议验收。

---

## 13. 开发原则

1. Self-host 默认组件越少越好。
2. PostgreSQL 能承担的结构化状态不要拆新数据库。
3. 本地 Volume 能满足默认文件存储时不要强制 MinIO。
4. Keycloak/OIDC 只作为可选企业扩展，不成为默认依赖。
5. Firebase/GCP 保留 adapter，不阻塞无 GCP 启动。
6. 认证、Tenant、权限必须 server-authoritative / fail-closed。
7. 不信任前端传入 tenant/group/role claims。
8. A2UI/AG-UI/MCP 标准链路优先保持 upstream-compatible。
9. 新功能优先放 provider/adapter/config 层。
10. 每个阶段都必须更新 Issue + HANDOFF，禁止再次出现“文档说没开始、代码已经完成”的状态漂移。
