# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：2026-09-14  
> 当前阶段：**Self-host 核心持久化能力已经实装，当前主线进入内置 JWT / 无 GCP 生产认证改造。**

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

当前真正阻塞“生产级自托管”的首要问题已经从数据库/文件存储转为：

1. #7 Built-in JWT + PostgreSQL identity
2. #8 GCP 能力彻底 optional
3. #1/#2/#3 最终真实协议验收与 Issue 收口
4. #9～#11 多租户/模型/MCP 管理产品化

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

## 8. 当前最重要任务：#7 Built-in JWT

这是现在 Self-host 走向“生产可用”的最大缺口。

当前 Self-host 虽然数据、Session、Memory、文件都已持久化，但 Compose 仍然依赖：

```env
LOCAL_MODE=1
```

意味着身份仍是 dev stub，不应视为正式生产认证。

#7 的目标是：

```text
PostgreSQL
├── auth users
├── tenant identity
├── roles / group tags
└── credential metadata

FastAPI
├── login
├── password verification
├── JWT issue/verify
├── expiry / issuer / audience
└── request User / AccessContext
```

推荐 backend selector：

```env
AUTH_BACKEND=local-jwt|firebase|stub|oidc
```

第一阶段最小闭环必须做到：

- PostgreSQL 本地账号
- 安全 password hash
- JWT 登录
- JWT 校验
- server-authoritative tenant/domain/groupTags
- platform admin / tenant admin 复用现有 `AccessContext`
- 所有现有 `Depends(get_current_user)` 无需业务层大改
- Firebase 保持兼容

OIDC 可以作为第二步，不阻塞最小 Self-host。

---

## 9. #8 GCP optionalization

#7 完成后立即推进。

目标是在完全没有以下配置时：

```text
gcloud / ADC
Firebase
Vertex Agent Engine
GCS
Cloud Trace / Cloud Logging
```

仍然可以完整运行：

```text
Chat
Skill
MCP
MCP Apps
AG-UI
A2UI
Session
Memory
Files
Auth
```

GCP 能力继续以可选 adapter/provider 形式存在。

---

## 10. 后续产品化顺序

建议严格按：

```text
#7 Built-in JWT
 ↓
#8 GCP optionalization
 ↓
收口 #1 / #2 / #3
 ↓
#9 explicit Tenant model
 ↙                 ↘
#10 Model Provider UI   #11 MCP Server UI
           \            /
            #12 i18n/branding
                   ↓
            #13 GHCR/release
```

#14 upstream sync 必须贯穿整个过程。

#16 S3-compatible 只在有实际需求时推进。

---

## 11. 自托管启动

```bash
cp .env.selfhost.example .env
# 配置至少一个 LLM provider

docker compose up -d --build
```

默认 persistence：

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
OBJECT_STORAGE_BACKEND=local
```

当前仍需注意：在 #7 完成之前，Compose 的身份边界仍属于 LOCAL_MODE/stub，不应直接当成公网生产认证。

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
