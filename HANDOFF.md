# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：**2026-09-16**  
> 当前主线：**Self-host 基线、Tenant 核心边界、MCP 管理面、Model Provider/Model/Tenant Policy、legacy ownership migration 代码均已完成；当前剩余主要是真实 Provider、真实 MCP、真实 Tenant A/B 和浏览器协议验收。**

---

## 1. 当前结论

这个仓库已经进入“真实环境验收与发布收口”阶段，不应再把工作重点描述为基础架构建设。

当前 `main` 已具备：

- PostgreSQL Repository / persistence abstraction
- PostgreSQL ADK Session
- PostgreSQL durable Memory
- PostgreSQL 下 A2UI surface / `clientDataModel` / `lastAction` 恢复
- Local ObjectStorage + Docker Volume
- ADK `FileArtifactService` 本地持久化
- Built-in local JWT
- 无 GCP 凭证/资源依赖的 Self-host 主路径
- 显式 `tenant_id` 与 fail-closed tenant boundary
- Tenant-aware Session / Document / Folder / Artifact / MCP / Audit / Budget
- Stable Tenant Tool Permission
- legacy ownership 可审计迁移 + rollback journal
- MCP Server Admin API + Admin UI + Health / Discovery + Skill Binding
- YAML bootstrap + Database dynamic model overlay
- 多 OpenAI-compatible Provider 独立 `base_url / api_key_ref`
- Dynamic Model 进入 ADK Agent runtime
- Platform default + `default/smart/fast` tier mapping
- First-class Tenant `allowedModels / defaultModel`
- 已认证 `/api/models` Tenant 白名单过滤
- Agent runtime Tenant Model Policy enforcement
- Self-host / Core Runtime / Tenant / MCP / Model Provider 专项 CI Gate

当前主要剩余：

1. #10 / #2：真实第三方 OpenAI-compatible Provider → Model → Skill → Agent → Tool Calling E2E。
2. #9：在目标部署执行 legacy migration，并做 Tenant A/B 真实隔离 E2E。
3. #11：真实 Self-host MCP 管理/Tool Call/MCP Apps E2E。
4. #1/#2/#3：真实浏览器完成 AG-UI / A2UI / MCP Apps / Skill 等统一协议验收。
5. 后续推进 #12 中文化、#13 GHCR/版本发布、#14 upstream sync。

---

## 2. 平台核心架构

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

Self-host 改造没有替换上游标准协议链路。

继续遵守：

- 不自造 A2UI 协议
- 不破坏 AG-UI event path
- MCP Apps 保持独立 sandbox/origin
- Google Cloud 能力以 adapter/provider 形式保留
- 新能力优先放 Repository / Provider / Adapter / Config 层
- Tenant / Auth / Permission 必须 server-authoritative / fail-closed
- 上游兼容优先

---

## 3. Self-host 默认架构

```text
Browser
   ↓
Frontend :3456
   ↓
Backend :1956
   ├── Google ADK Runtime
   ├── Runtime Skills
   ├── AG-UI / A2UI
   ├── MCP / MCP Apps
   ├── Model Provider Registry
   │
   ├── PostgreSQL :5432
   │    ├── platform / tenant data
   │    ├── ADK Session + events/state
   │    ├── durable Memory
   │    ├── MCP Server Registry
   │    └── Dynamic Model Registry
   │
   └── /data
        ├── objects
        └── artifacts

MCP Apps sandbox :3457
```

正式 Self-host 默认：

```env
SELF_HOSTED_MODE=1
LOCAL_MODE=0
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
AUTH_BACKEND=local-jwt
OBJECT_STORAGE_BACKEND=local
```

默认不要求 Redis、MinIO、Keycloak、Firebase、GCP project/ADC、独立 Session DB、独立 Memory DB、消息队列或独立向量数据库。

---

## 4. 冻结部署分支

稳定部署快照：

```text
deploy/2026-09-15
```

冻结 SHA：

```text
e07dbe78da4ec5ba06866ca423707c9eb50d9329
```

**不要移动、重写或自动合并后续 `main` 到该分支。**

后续需要稳定版本时创建新的 deploy branch，例如：

```text
deploy/2026-09-16
deploy/2026-09-16-r2
```

不要修改原冻结快照。

当前 `main` 已包含冻结分支之后的 #19、#20、#21、#23～#31 等后续能力。

### 当前 main 最近关键合并

```text
PR #30 — Tenant Model Policy
merge SHA: 5d55ee76d8a569c3c49b8b9814877a9d93a6ab4f

PR #31 — legacy ownership migration + stable Tenant Tool Permission + rollback journal
merge SHA: bd75d3abf679a503d9d072754b3873bed350687e
```

---

## 5. Issue 总状态

### 已完成 / 已关闭

- #4 PostgreSQL Persistence ✅
- #5 Session / Memory / A2UI reconstruction ✅
- #6 ObjectStorage / Artifact ✅
- #7 Built-in JWT ✅ Closed
- #8 GCP optionalization ✅ Closed

### 代码主体已完成，等待真实部署 / 协议验收

- #1 Self-host 全链路基线 — OPEN
- #2 通用 OpenAI-compatible — OPEN
- #3 Docker Compose Self-host — OPEN
- #9 显式 Tenant / 隔离 / migration — OPEN
- #10 Model Provider 配置中心 — OPEN
- #11 MCP Server 管理能力 — OPEN

这些 Issue 不能只因为单测/CI 通过而关闭。

---

## 6. #1 / #2 / #3 Self-host 与 OpenAI-compatible

已有：

- `scripts/smoke-selfhost.sh`
- Self-host baseline CI
- Self-host no-GCP gate
- PostgreSQL Session / Memory / A2UI reconstruction regression
- MCP / OpenAI-compatible regression
- local-jwt 登录路径
- 生产式 Docker Compose

OpenAI-compatible 当前支持：

```text
YAML / legacy model
    ↓
OPENAI_API_BASE + OPENAI_API_KEY

Dynamic Model
    ↓
provider_id
    ↓
Model Provider Registry
    ↓
provider.baseUrl + provider.apiKeyRef
```

可用于 DeepSeek / Qwen compatible endpoint / vLLM / LiteLLM Proxy / OneAPI / NewAPI / 内部兼容网关。

真实关闭前仍需浏览器/真实 Provider 验证：

1. 普通 Chat
2. Runtime Skill
3. 真实 Provider completion
4. 真实 Tool Calling
5. MCP Tool
6. MCP App iframe/resource
7. A2UI surface
8. A2UI action round-trip

---

## 7. #9 Tenant / 隔离 / legacy ownership — 代码侧已收口

### 已完成

- 稳定 `tenant_id`，domain 仅为兼容 identity mapping
- User / Skill / Session / Document / Folder / Artifact / MCP / Audit tenant scope
- tenant-aware 核心资源默认 fail-closed
- MCP Registry / Proxy / cache tenant partition
- Audit `tenantId / actorTenantId`
- PostgreSQL Session / Memory / A2UI 使用稳定租户上下文
- Local ObjectStorage / Artifact tenant-safe namespace
- tenant budget extension point
- `identity_key: tenant_id`
- `missing_identity_policy: block`
- 同 UID 跨租户 / public ACL 跨租户安全回归
- Tenant Model Policy 基于 first-class `tenants/{tenant_id}.modelPolicy`
- legacy `clients/{domain}` 不允许通过模型策略 API 隐式迁移

### PR #31：Stable Tenant Tool Permission

运行时顺序：

```text
user-specific rule
      ↓
stable tenant rule: tenant:<tenant_id>
      ↓
legacy domain rule
      ↓
wildcard
      ↓
deny
```

安全语义：

- Permission cache 按 stable tenant 分区
- 带 `tenantId` 的 user-specific rule 必须匹配当前 trusted tenant
- legacy domain rule 在 first-class tenant 已存在时必须证明 domain 属于当前 tenant
- 旧的无归属 user/domain permission 仍可作为 migration bridge，但只能由 Platform Admin 管理
- Tenant Admin 不能管理其他 Tenant 的 permission

### PR #31：Legacy ownership migration

核心文件：

```text
backend/scripts/migrate_tenants.py
backend/scripts/tenant_migration_journal.py
docs/tenant-ownership-migration.md
```

迁移支持：

- `clients/{domain}` → first-class `tenants/{tenant_id}` + `tenant_domains`
- 显式 `domain=tenant_id` mapping
- 多历史 domain 合并到同一 stable tenant
- local JWT 缺失 `tenantId` 时可信 backfill
- 已有显式 `auth_users.tenantId` 保持权威，不按邮箱覆盖
- `tenant-admin:{domain}` → `tenant-admin:{tenant_id}`
- agreeing legacy domain Tool Permission → `tenant:<tenant_id>`
- user-specific Tool Permission 仅在可与可信 local user 精确关联时补 ownership
- Audit 仅在 target ownership 可明确证明时 backfill
- 不从 `actorEmail` 推断 Audit Tenant
- ambiguous ownership 保持 platform-only

默认只 dry-run；实际写入必须显式：

```bash
uv run python scripts/migrate_tenants.py \
  --map legacy.example=tenant-a \
  --apply
```

每个 apply run 生成 migration run id。

回滚：

```bash
uv run python scripts/migrate_tenants.py --rollback <RUN_ID>
```

rollback 特性：

- 先对全部 operation 做 drift preflight
- 任一迁移后数据发生业务修改则拒绝回滚
- migration 新建文档回滚时删除
- pre-existing 文档仅恢复迁移修改过的字段
- `auth_users.passwordHash` 等敏感字段不复制到 journal
- journal 查询 provider-neutral，不依赖 Firestore 复合索引

### #9 当前剩余

不得关闭 #9，直到完成：

1. 在目标部署执行 dry-run。
2. 人工复核 ambiguous ownership。
3. 执行 apply / verify。
4. 验证 rollback 路径。
5. Tenant A/B 真实 E2E：
   - Session
   - 文件
   - Skill 私有配置
   - MCP
   - Audit
   - quota
   - Tool Permission
   - Model whitelist/default

Issue #9 已同步到这一状态。

---

## 8. #10 Model Provider 配置中心 — 代码侧已完成

关键合并：

```text
PR #25 — Provider / Dynamic Model backend
6c0523de8166026850779df22a4a4bbad34af993

PR #26 — Effective Model Registry
05709e32a6cb1302e2ac46f332ebd0761ab7942b

PR #27 — Agent Runtime Provider Routing
aaf1d1de443fcd595da23f21117ddac3493fcd09

PR #28 — Model Providers Admin UI + Probe
2ad75f959a777cb4c3de151e22bd847b71cfedaf

PR #29 — Platform Default + Tier Mapping
b58fadb92392f564f95027987f1020cf36690069

PR #30 — Tenant Model Policy
5d55ee76d8a569c3c49b8b9814877a9d93a6ab4f
```

已实现：

- Provider CRUD
- Dynamic Model CRUD
- `${ENV_VAR}` Secret Reference
- Provider connectivity test
- completion probe
- Tool Calling probe
- effective registry overlay
- runtime Provider routing
- 多 Provider 独立 `baseUrl / apiKeyRef`
- Platform default model
- `default / smart / fast` managed tier mapping
- Tenant `allowedModels / defaultModel`
- 已认证 `/api/models` Tenant filter
- primary/fallback runtime enforcement
- Platform Admin 管理 Tenant Model Policy
- legacy tenant 不被 model-policy API 隐式迁移

### #10 当前剩余

必须使用真实第三方 OpenAI-compatible endpoint 验证：

```text
Provider test
    ↓
Dynamic Model
    ↓
Completion probe
    ↓
Tool Calling probe
    ↓
Skill Studio 选择模型
    ↓
Agent conversation
    ↓
真实 Tool Calling
```

如果当前没有真实 endpoint / secret，不要使用 mock 关闭 #10。

---

## 9. #11 MCP Server 管理 — 代码侧已完成

已实现：

- MCP Server CRUD
- Platform / Tenant scope
- HTTP / SSE / Streamable HTTP
- Docker service / local network URL
- Auth Header / Secret Reference
- Secret redaction / audit redaction
- Registry cache invalidation
- Health
- Discovery
- `initialize`
- `tools/list`
- `resources/list`
- `prompts/list`
- MCP Apps resource URI summary
- Admin UI
- Skill Binding
- disabled server runtime fail-closed
- Self-host MCP Server example
- `docs/selfhost-mcp-server.md`

### #11 当前剩余

真实 Self-host 部署验证：

1. UI 新增 Server
2. Health 成功
3. Discovery 成功
4. 绑定指定 Skill
5. Agent 真实 MCP Tool Call
6. MCP Apps Server 前端真实资源渲染

---

## 10. Secret / Credential 原则

```text
配置层保存 Secret Reference
        ↓
运行时解析
        ↓
只传给实际客户端
```

禁止：

- Admin API 返回 API Key 明文
- Admin UI 回显 API Key 明文
- Audit 记录 Secret 值
- migration journal 复制密码哈希/无关身份秘密
- Secret 缺失时静默切换到其他 Provider 凭证

未来即使加入正式 Secret Store，也继续保留 `secret_ref` 模型。

---

## 11. 当前 CI / 验证边界

专项 gate：

- Tenant isolation
- Core runtime persistence
- Self-host no-GCP
- Self-host baseline
- Self-host auth baseline
- MCP admin gate
- Model provider gate

PR #31 最新 head 在合并前确认：

- Tenant Isolation ✅
- Core Runtime Persistence ✅
- Self-host baseline ✅
- Self-host auth baseline ✅
- Self-host no-GCP ✅
- MCP Admin ✅

Tenant Isolation 包含 stable tenant tool permission、Admin scope、migration apply/rollback、drift rejection、secret exclusion 等回归。

**CI 不能替代真实协议/部署验收。**

---

## 12. 自托管启动

冻结快照：

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
git checkout deploy/2026-09-15
cp .env.selfhost.example .env
docker compose up -d --build
```

当前 main：

```bash
cp .env.selfhost.example .env
make docker-up
```

端口：

```text
Frontend      3456
Backend       1956
MCP sandbox   3457
PostgreSQL    5432
```

注意：`main` 已包含冻结快照之后的 #25～#31 等能力，不等同于 `deploy/2026-09-15`。

---

## 13. 下一步执行顺序

### 第一优先：#10 / #2 真实 Provider E2E

如果有真实 endpoint / secret，直接完成：

```text
Provider → Model → Completion → Tool Calling → Skill → Agent
```

没有真实凭证时不要 mock 验收，转第二优先。

### 第二优先：#9 目标部署 migration + Tenant A/B E2E

代码侧 migration / rollback 已完成，**不要重新实现迁移脚本**。

接下来做：

1. dry-run
2. review mapping / ambiguous ownership
3. apply
4. verify
5. rollback exercise
6. Tenant A/B E2E

### 第三优先：#11 MCP 真实自托管验收

```text
UI Add Server → Health → Discovery → Binding → Tool Call → MCP Apps rendering
```

### 第四优先：#1/#2/#3 统一浏览器协议验收

一次真实 Self-host acceptance 同时覆盖 Chat / Skill / MCP / MCP Apps / A2UI / OpenAI-compatible。

### 后续

- #12 中文化 / Branding
- #13 GHCR / versioned release
- #14 upstream sync
- #16 S3-compatible optional adapter
- #17 OIDC enterprise extension

---

## 14. 开发约束

1. Self-host 默认依赖越少越好。
2. PostgreSQL 能承担的结构化状态不要拆新数据库。
3. 默认文件持久化继续使用 local volume，不强制 MinIO。
4. Keycloak / OIDC 保持可选，不成为默认部署前置条件。
5. Firebase / GCP 能力保留 adapter，不阻塞无 GCP 启动。
6. Tenant / Auth / Permission 一律 server-authoritative / fail-closed。
7. 不信任前端传入的 tenant / group / role claims。
8. MCP / A2UI / AG-UI 保持标准协议优先。
9. Dynamic Model 不得绕过统一 Registry / runtime resolver。
10. Provider API Key / MCP credential 不允许通过普通 API 明文返回。
11. Tenant Model Policy 必须基于 first-class tenant id。
12. migration 只迁可信 ownership；不通过邮箱猜测历史数据归属。
13. 不要修改冻结的 `deploy/2026-09-15`。
14. 每个阶段结束后同步 Issue + HANDOFF。
