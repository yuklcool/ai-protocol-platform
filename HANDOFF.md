# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：**2026-09-16**  
> 当前阶段：**核心 Self-host / Tenant / Provider / MCP 能力已经完成，当前同时推进真实 Provider 最终验收与 versioned GHCR 发布收口。PR #35 是真实 Provider + Agent + MCP 的最终验收 harness；PR #36 是 GHCR/Release 发布链。**

---

## 1. 当前结论

当前 `main` 已具备：

- PostgreSQL Repository / Persistence
- PostgreSQL ADK Session + durable Memory
- PostgreSQL A2UI state reconstruction
- Local ObjectStorage + Artifact Volume
- Built-in local JWT
- 无 GCP 凭证/资源依赖的正式 Self-host 主路径
- 显式 stable `tenant_id` 与 fail-closed tenant boundary
- Tenant-aware Session / Document / Folder / Artifact / MCP / Audit / Budget
- Stable Tenant Tool Permission
- legacy ownership 可审计迁移 + rollback journal
- 真实 Compose/PostgreSQL/local-jwt Tenant A/B isolation gate
- MCP Server Admin API/UI + Health / Discovery + Skill Binding
- 真实 Self-host MCP Admin → Skill Binding → Proxy → MCP Apps HTML transport gate
- 真实 Chromium MCP Apps separate-origin sandbox/iframe rendering gate
- Dynamic Model / Provider registry
- 多 OpenAI-compatible Provider 独立 `baseUrl / apiKeyRef`
- Platform Default + `default/smart/fast` tier mapping
- Tenant Model `allowedModels / defaultModel`
- Model Provider / Tenant / MCP / Core Runtime / Self-host 专项 CI

当前**不要重新实现**以上基础能力。

现在真正剩余的是两条主线：

1. **真实 Provider 最终验收**：#10 / #11 / #9 / #2 的 LLM-dependent 边界。
2. **发布收口**：#13 GHCR/versioned release，目前由 PR #36 推进。

---

## 2. Self-host 默认架构

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
   │    ├── ADK Session
   │    ├── durable Memory
   │    ├── MCP Registry
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

默认不要求 Redis、MinIO、Keycloak、Firebase、GCP project/ADC、独立 Session DB、独立 Memory DB 或消息队列。

---

## 3. 冻结部署快照

冻结分支：

```text
deploy/2026-09-15
```

冻结 SHA：

```text
e07dbe78da4ec5ba06866ca423707c9eb50d9329
```

**禁止移动、重写或把后续 `main` 自动合并到该分支。**

需要新稳定版本时创建新的 deploy branch。

---

## 4. 最近关键合并与当前开放 PR

### 已合并

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

PR #31 — Legacy ownership migration + Stable Tenant Tool Permission + rollback journal
bd75d3abf679a503d9d072754b3873bed350687e

PR #32 — Real Tenant A/B self-host isolation acceptance
9a7fe9b06dd30d5d2e9166b669c846719e3c7675

PR #33 — Real Self-host MCP protocol acceptance
96d3f03bfe3dcb109b39db5ebd74adc16c466f10

PR #34 — Real MCP Apps Chromium browser/sandbox acceptance
aaab15e913d392ac4b84a041be43a4fc2e175105
```

### 当前开放

#### PR #35 — `test(provider): add real Provider Agent MCP acceptance`

分支：

```text
feat/real-provider-agent-mcp-acceptance
```

Head：

```text
5aba8b77f15bb609f2018abee290096d74f6cdb4
```

状态：**OPEN，mergeable。**

该 PR 新增最终真实 Provider 验收 harness，但**没有声称真实第三方 Provider 已通过**。真实 job 仅通过 `workflow_dispatch` 运行，并要求 operator 提供真实 OpenAI-compatible endpoint / model / secret。

验收目标：

```text
Persisted Provider
  ↓
Provider /models connectivity
  ↓
Dynamic Model
  ↓
real completion probe
  ↓
real forced tool-calling probe
  ↓
真实 ext-apps MCP Server
  ↓
private Skill + Dynamic Model + MCP binding
  ↓
正常 Chromium /chat/{skillId}
  ↓
真实用户输入
  ↓
模型真实选择并执行 show-map
  ↓
MCP App iframe
  ↓
post-tool assistant final response
```

缺少 `REAL_PROVIDER_API_KEY`、endpoint、模型或任意一步失败都应 fail closed。

#### PR #36 — `feat(release): add versioned GHCR self-host delivery`

分支：

```text
feat/ghcr-selfhost-release
```

当前 Head（更新 HANDOFF 前）：

```text
07936bf26a0fb4b0ddd1c6e746c200c31b2e49b6
```

状态：**OPEN，mergeable；当前正在修 frontend release image CI blocker。**

本交接文档当前就是在该分支更新。

---

## 5. #9 Tenant / Isolation 状态

#9 的代码侧已经收口，Issue 保持 OPEN 只因为真实目标部署迁移和 LLM-dependent acceptance 尚未完成。

### 已完成的运行时边界

- stable `tenant_id`；domain 仅是 compatibility identity mapping
- Session / Document / Folder / Artifact / MCP / Audit tenant scope
- tenant-aware 资源默认 fail-closed
- tenant budget extension point
- `identity_key: tenant_id`
- `missing_identity_policy: block`
- Tenant Model Policy
- 同 UID 跨 Tenant 安全回归

### Stable Tenant Tool Permission

查找顺序：

```text
user-specific
   ↓
tenant:<tenant_id>
   ↓
legacy domain
   ↓
wildcard
   ↓
deny
```

约束：

- cache 按 stable tenant 分区
- 带 `tenantId` 的 user rule 必须匹配当前 trusted tenant
- first-class tenant 下 legacy domain rule 必须证明 domain 属于当前 tenant
- 无可信归属的旧 permission 继续 platform-only

### Production migration

核心文件：

```text
backend/scripts/migrate_tenants.py
backend/scripts/tenant_migration_journal.py
docs/tenant-ownership-migration.md
```

支持：

- `clients/{domain}` → `tenants/{tenant_id}` + `tenant_domains`
- 显式 domain→tenant mapping
- 多历史 domain 合并
- local JWT 缺失 `tenantId` 的可信 backfill
- 已存在显式 `tenantId` 保持权威
- tenant-admin tag rewrite
- legacy Tool Permission ownership migration
- 可证明 target ownership 的 Audit backfill
- ambiguous ownership 保持 platform-only
- apply run journal
- drift-safe rollback
- journal 不复制 password hash 等身份秘密

迁移默认 dry-run：

```bash
uv run python scripts/migrate_tenants.py --map old.example=tenant-a
```

实际写入：

```bash
uv run python scripts/migrate_tenants.py \
  --map old.example=tenant-a \
  --apply
```

回滚：

```bash
uv run python scripts/migrate_tenants.py --rollback <RUN_ID>
```

### PR #32：真实非 LLM Tenant A/B E2E

新增：

```text
backend/scripts/seed_tenant_acceptance.py
scripts/smoke-tenant-isolation.sh
.github/workflows/tenant-live-acceptance.yml
```

该 gate 使用真实：

```text
Docker Compose
+ PostgreSQL
+ Backend HTTP
+ local-jwt
+ local ObjectStorage
```

并故意使用**相同 UID、不同 stable tenant** 的两个账号，已通过：

- trusted `/api/auth/whoami` tenant identity
- Tenant Admin own/cross scope
- public Session 仍不可跨 Tenant
- `/api/sessions` 在相同 UID 下仍按 Tenant 分区
- 相同 UID + 相同文件名真实上传，metadata/ObjectStorage 仍隔离
- authenticated `/api/models` Tenant policy filtering
- stable Tool Permission admin scope
- tenant-scoped MCP config visibility
- tenant-scoped Admin Audit

### #9 真正剩余

1. 在目标真实部署对已有 legacy 数据执行 dry-run / review / apply / verify。
2. 人工处理 ambiguous ownership。
3. 在目标部署演练 rollback。
4. 接入真实 Provider 后验证 Tenant A/B 实际模型调用使用独立 quota bucket。
5. 用真实 Agent Tool Calling 验证 Tool Permission / Model Policy 无法跨 Tenant 绕过。

不要重复实现 Session/文件/MCP config/Audit/Model Policy 的 Tenant A/B 非 LLM 验收；PR #32 已覆盖。

---

## 6. #10 Model Provider 状态

代码侧已完成：

- Provider CRUD
- Dynamic Model CRUD
- `${ENV_VAR}` Secret Reference
- Provider connectivity
- completion probe
- Tool Calling probe
- database overlay + YAML baseline
- Agent runtime Provider routing
- 多 Provider 独立 Base URL / Secret
- Platform default model
- `default/smart/fast` managed tier
- Tenant `allowedModels/defaultModel`
- authenticated `/api/models` filter
- primary/fallback runtime policy enforcement

#10 不应再开发第二套 Provider 系统。

### #10 当前唯一关键缺口

使用一个真实的非 OpenAI、OpenAI-compatible endpoint 完成：

```text
Provider Test
   ↓
Dynamic Model
   ↓
Completion Probe
   ↓
Tool Calling Probe
   ↓
Skill Studio model selection
   ↓
Agent conversation
   ↓
Actual Tool Calling
```

PR #35 已经把这条验收链做成 manual-only fail-closed workflow；下一步是提供真实 endpoint / secret 并跑通。

没有真实 endpoint / secret 时，不得用 mock 关闭 #10。

---

## 7. #11 MCP Server 管理状态

除真实模型驱动 Tool Calling 外，MCP 管理、协议和浏览器渲染链路已经完成。

已有：

- MCP Server CRUD
- Platform / Tenant scope
- HTTP / SSE / Streamable HTTP
- local/Docker network URL
- Secret Reference / redaction
- Health / real `initialize`
- Discovery: `tools/list` / `resources/list` / `prompts/list`
- MCP Apps resource URI summary
- Admin UI
- Skill Binding
- disabled fail-closed
- Self-host MCP example
- `docs/selfhost-mcp-server.md`

### PR #33：真实 Self-host MCP Protocol Acceptance

真实验收路径已经通过：

```text
local-jwt login
  ↓
/api/skills 创建 private Skill
  ↓
/api/admin/mcp-servers 注册真实 Docker-network MCP Server
  ↓
Admin Health -> real initialize
  ↓
Admin Discovery -> map tool + ui:// resource
  ↓
未绑定 Skill：/mcp/{server_id} -> 403
  ↓
普通 Skill API 绑定 MCP server
  ↓
Python MCP SDK 经平台 /mcp Proxy
  ↓
initialize
  ↓
tools/list
  ↓
resources/list / resources/read
  ↓
真实 ui:// 非空 text/html MCP Apps 资源
  ↓
Disable Server
  ↓
Admin Health 仍可诊断；Runtime Proxy -> 404
```

### PR #34：真实 Chromium MCP Apps Browser Acceptance

PR #34 复用现有正式产品 Host 链路，没有新造第二套 Host：

```text
MessageBubble
  ↓
MCPAppToolCallRouter
  ↓
@mcp-ui/client AppRenderer
  ↓
Browser MCP Client
  ↓
Authenticated platform /mcp Proxy
  ↓
真实 ext-apps map MCP Server
  ↓
listTools + resources/read
  ↓
ui://cesium-map/mcp-app.html
  ↓
Host :3456
  ↓
Separate-origin sandbox :3457
  ↓
Inner MCP App iframe
```

CI 使用真实 Compose + PostgreSQL + Backend/local-jwt + Frontend + MCP sandbox + upstream ext-apps map MCP Server + Chromium/Playwright。

已确认：

- real local-jwt browser session
- MCP Admin register / Health / Discovery
- Skill Binding
- authenticated Proxy
- `show-map` tool definition 可发现
- 真实 `ui://` HTML resource 可读取
- Host origin 与 Sandbox origin 分离
- Sandbox 创建 inner iframe
- 真实 MCP App HTML 写入 iframe 并被 Chromium 观察到
- 无 sandbox ready timeout / origin rejection / listTools / readResource fatal error

该 gate 只固定“LLM 产生 ToolCall”这一环；其余 MCP/Browser/Sandbox 链路都是真实的。

### #11 真正剩余

只剩：

1. **真实 Provider 驱动 Agent MCP Tool Call**。

这已经由 PR #35 的 manual acceptance harness 覆盖测试设计；尚缺真实 Provider secret/endpoint 的实际执行结果。

不要再重复实现或验收 Admin register / Health / Discovery / Binding / Proxy / Apps resource transport / browser sandbox rendering；PR #33 + #34 已覆盖。

---

## 8. #13 GHCR / Versioned Release 状态（PR #36）

这是当前正在推进的新主线。

### 8.1 目标

让 Self-host 用户不需要 clone 仓库、不需要本地 build，直接使用 versioned prebuilt images 部署：

```text
GitHub Release assets
+ docker-compose.release.yml
+ .env.selfhost.example
+ GHCR backend image
+ GHCR frontend image
+ GHCR mcp-sandbox image
```

### 8.2 PR #36 已实现的代码

新增/修改包括：

```text
.github/workflows/release-images.yml
docker-compose.release.yml
backend/scripts/apply_selfhost_migrations.py
backend/Dockerfile
frontend/Dockerfile
frontend/docker-entrypoint.sh
docs/selfhost-release-images.md
README.md
SELFHOST.md
scripts/smoke-selfhost.sh
```

核心能力：

- backend / frontend / mcp-sandbox 三个 GHCR release image
- SHA tag
- semver tag
- release `latest` tag
- tag release 时 `linux/amd64 + linux/arm64`
- BuildKit SBOM
- provenance attestation
- Trivy HIGH/CRITICAL vulnerability gate
- GitHub Release 自动生成 release notes
- Release 附带 `docker-compose.release.yml` 与 `.env.selfhost.example`
- `docker-compose.release.yml` 不含 build context，不依赖源码 bind mount
- backend image 自带 PostgreSQL migration runner
- migration journal：`platform_schema_migrations`
- source Self-host 路径同样改为幂等 migration runner
- frontend release image 支持 MCP Sandbox URL runtime relocation 设计
- Self-host 文档已经修正旧的 `LOCAL_MODE=1`、旧 tenant/domain 和 MCP 手工验收描述

### 8.3 已通过的真实 Release Gate

Workflow run：

```text
35060818996
```

`Release self-host gate` 已完整成功，证明：

1. source Compose 可解析。
2. release Compose 可解析。
3. frontend typecheck + unit tests 通过。
4. source backend / frontend / mcp-sandbox 三镜像 build 通过。
5. 真实 PostgreSQL + backend + frontend + sandbox 栈启动成功。
6. `LOCAL_MODE=0` 的 production-style no-GCP smoke 通过。
7. backend 启动时 bundled migration 实际执行成功。
8. PostgreSQL 中实际存在：

```text
platform_schema_migrations
└── 001_postgres_documents.sql
```

因此，**镜像内 migration runner / 启动顺序 / production-mode Self-host smoke 已经真实验证通过。**

### 8.4 Release image matrix 当前结果

同一 run：

```text
backend image      ✅ success
mcp-sandbox image  ✅ success
frontend image     ❌ failure
```

frontend 当前硬阻塞并不是 TypeScript 或 Next.js 编译错误，而是 release build 使用的专用 placeholder：

```text
__MCP_SANDBOX_PUBLIC_URL__
```

在 Next.js prerender `/dev/mcp-apps/active` 时被 `new URL(...)` 提前解析，导致：

```text
TypeError: Invalid URL
input: '__MCP_SANDBOX_PUBLIC_URL__'
ERR_INVALID_URL
```

因此当前 frontend release image 尚未成功生成，后面的“启动容器后把 placeholder 替换成 `MCP_SANDBOX_PUBLIC_URL`”验证也尚未执行。

### 8.5 当前正确的修复方向

不要放弃“同一预构建 frontend image 可部署到任意域名”这个目标。

需要把 placeholder 改成**build-time 也合法的 URL 字符串**，同时保持它足够唯一，容器 entrypoint 仍可在启动时替换成：

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
```

修复后必须重新验证：

```text
frontend release image build
  ↓
container entrypoint runtime replacement
  ↓
placeholder 完全消失
  ↓
目标 MCP_SANDBOX_PUBLIC_URL 出现在 .next runtime assets
```

### 8.6 额外观察

frontend Dockerfile 仍基于 Node 18；当前依赖里已经出现多个 `>=20` engine warning，包括 `@modelcontextprotocol/ext-apps` / jsdom 相关包。

这不是本轮 hard failure 的直接原因，但在 release image 稳定化时应考虑把 frontend build/runtime Node 基线提升到 Node 20/24，避免后续依赖升级直接变成安装/构建失败。

### 8.7 #13 还不能关闭的原因

PR event 下目前还**没有**证明：

- frontend release image build 成功
- runtime sandbox URL replacement 成功
- tag 触发的 GHCR push 成功
- `linux/amd64 + linux/arm64` 真正发布成功
- SBOM/provenance 真正随 release image 生成
- Trivy 发布后镜像扫描通过
- GitHub Release 实际创建成功
- 完全 no-clone、pull-only 的 `docker-compose.release.yml` 从 GHCR 冷启动成功

所以 #13 当前应保持 OPEN。

---

## 9. Issue 总状态

已关闭/完成基础能力：

- #4 PostgreSQL Persistence ✅
- #5 Session / Memory / A2UI reconstruction ✅
- #6 ObjectStorage / Artifact ✅
- #7 Built-in JWT ✅
- #8 GCP optionalization ✅

保持 OPEN、等待最终真实验收或发布收口：

- #1 Self-host 全链路
- #2 OpenAI-compatible real Provider E2E
- #3 Docker Compose release acceptance
- #9 target migration + quota/Tool Calling final acceptance
- #10 real Provider E2E
- #11 real Agent MCP Tool Call
- #13 GHCR / versioned release（PR #36）

---

## 10. 当前 CI Gate

当前已有：

- Tenant isolation
- Tenant live self-host acceptance
- Core runtime persistence
- Self-host baseline
- Self-host auth baseline
- Self-host no-GCP
- MCP admin
- MCP live self-host acceptance
- Chromium separate-origin MCP Apps browser acceptance
- Model provider
- **Self-host release images（PR #36 新增）**

### 真实能力边界

已经被真实 CI 证明：

- PostgreSQL persistence / Session / Memory / A2UI
- no-GCP Self-host
- local-jwt
- Tenant A/B 非 LLM isolation
- MCP Admin / Binding / Proxy / HTML resource transport
- Chromium MCP Apps separate-origin sandbox rendering
- release stack production-mode no-GCP boot
- bundled PostgreSQL migration journal
- backend / mcp-sandbox release image PR build

仍不能由当前 CI 冒充：

- 真实第三方 Provider
- 真实 Agent MCP Tool Calling
- tag GHCR publish
- tag multi-arch publish
- tag SBOM/provenance/Trivy
- pull-only release Compose 冷启动

---

## 11. 下一步执行顺序

### 第一优先：收口 PR #36

当前立即动作：

```text
修 frontend build-safe placeholder
  ↓
重新跑 Self-host release images
  ↓
frontend image build 成功
  ↓
runtime MCP_SANDBOX_PUBLIC_URL replacement 验证成功
  ↓
确认所有相关 PR checks 全绿
  ↓
merge PR #36
```

PR #36 merge 后再做一次真正的 release/tag acceptance：

```text
创建新 version tag
  ↓
GHCR 三镜像 push
  ↓
amd64 + arm64
  ↓
SBOM + provenance
  ↓
Trivy
  ↓
GitHub Release assets
  ↓
只下载 compose/env
  ↓
docker compose pull/up
  ↓
no-clone cold-start smoke
```

只有这一步通过后，才能真正认为 #13 的发布链收口。

### 第二优先：PR #35 / #10 / #11 / #2 真实 Provider E2E

有真实 endpoint + secret 时执行：

```text
Provider
  ↓
Dynamic Model
  ↓
Completion Probe
  ↓
Tool Calling Probe
  ↓
Skill Studio model selection
  ↓
Agent Conversation
  ↓
模型真实选择 MCP Tool
  ↓
真实 MCP Server
  ↓
Tool result
  ↓
MCP App iframe
  ↓
Agent final response
```

这一轮可以同时收口：

- #10 real Provider E2E
- #11 real Agent MCP Tool Call
- #9 Tenant quota / Tool Permission / Model Policy 的 LLM-dependent final acceptance
- #2 OpenAI-compatible 全链路验收

### 第三优先：#9 目标部署 legacy migration

需要真实现存 legacy 数据，代码已经准备好；不要重新写 migration tooling。

执行：

```text
dry-run
  ↓
人工 review mapping / ambiguous ownership
  ↓
apply
  ↓
verify
  ↓
rollback drill
```

### 后续优化

核心验收/发布稳定后再推进：

- #12 中文化 / Branding
- #14 upstream sync
- #16 S3 adapter
- #17 OIDC extension

---

## 12. 开发约束

1. Self-host 默认依赖越少越好。
2. PostgreSQL 能承担的结构化状态不要拆新数据库。
3. 默认文件持久化使用 local volume，不强制 MinIO。
4. Keycloak/OIDC 保持可选。
5. GCP/Firebase 保留 adapter，不阻塞无 GCP 启动。
6. Tenant/Auth/Permission 必须 server-authoritative / fail-closed。
7. 不信任浏览器传入的 tenant/group/role。
8. MCP/A2UI/AG-UI 标准协议优先。
9. Dynamic Model 不得绕过统一 Registry/runtime resolver。
10. Provider API Key / MCP credential 不通过普通 API 明文返回。
11. Tenant Model Policy 必须使用 first-class tenant id。
12. migration 只迁可信 ownership，不通过邮箱猜历史归属。
13. 不修改冻结 `deploy/2026-09-15`。
14. 每个阶段结束后同步 Issue + HANDOFF。
15. 已由真实 gate 覆盖的能力不要重新造第二套验收；新增 gate 应聚焦尚未证明的边界。
16. PR CI 只证明 PR event 实际执行的步骤；tag-only GHCR push / multi-arch / SBOM / provenance / Trivy / GitHub Release 不能提前标记为已通过。
17. Release frontend 必须保持可重定位，不能重新把固定 `localhost:3457` 编译进通用 GHCR 镜像。
18. 未经真实 endpoint / secret 执行，不得把 PR #35 当成 real Provider acceptance 已通过。
