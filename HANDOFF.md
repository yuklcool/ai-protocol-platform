# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：**2026-09-18**  
> 当前主线：**基础设施和主要管理面代码已经完成，项目进入真实环境验收与发布收口阶段。#9 已完成 production migration tooling 和真实非 LLM Tenant A/B 自托管隔离验收；#10 剩真实第三方 Provider E2E；#11 已完成真实 MCP 后端/协议以及 Chromium separate-origin MCP Apps 浏览器渲染验收，只剩真实模型驱动 Agent MCP Tool Call。**

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

真实 Provider 验收入口：PR #35 已合并（`8445d6900b8422a203618de2fa8df9322b179561`），增加手动工作流 `Real Provider Agent MCP acceptance`；运行方式见 [docs/real-provider-acceptance.md](docs/real-provider-acceptance.md)。验收资源使用独立随机 ID，避免覆盖已有 MCP 配置。本地语法检查及 Playwright 用例收集通过；提交 `52f189a` 的 PR 语法 CI 与 MCP live self-host acceptance（含 Chromium）均通过，运行记录：[语法 CI](https://github.com/yuklcool/ai-protocol-platform/actions/runs/35071523277)、[MCP live CI](https://github.com/yuklcool/ai-protocol-platform/actions/runs/35071523241)。真实模型任务按 PR 触发规则跳过，尚未执行；需要配置 Actions secret `REAL_PROVIDER_API_KEY` 并提供 Base URL / model name。PR CI 通过不能替代真实模型验收，也不能据此关闭 #2/#10/#11。该脚本通过 API 创建 Skill，Skill Studio 模型选择 UI、Tenant LLM quota/policy 与目标数据迁移仍需独立验收。

接下来不要重新实现这些基础能力。当前最高优先级仍是使用真实第三方 Provider 完成模型、Agent、Tool Calling 全链路验收；其次是目标部署 legacy tenant migration。

2026-09-18 continuation: #16 S3-compatible ObjectStorage 已通过 PR #47 合并到 main。由于当前会话没有可用于 #2/#10/#11 最终验收的真实第三方模型 endpoint/secret，本轮开始推进不依赖外部模型密钥的 #17 OIDC optional extension。第一阶段分支 `feat/oidc-provider-baseline` 实现 OIDC discovery/JWKS bearer verification、issuer/audience/expiry/algorithm 校验、显式 issuer+sub -> local auth_users 映射、server-authoritative tenant/role 重载、provider capability/status API、subject-link CLI 与单元测试。Authorization Code + PKCE、nonce、frontend callback/sign-out 和 Keycloak 示例仍属于后续阶段，#17 不应在第一阶段合并后关闭。

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

**禁止移动、重写或把后续 `main` 自动合并到该分支。** 需要新稳定版本时创建新的 deploy branch。

当前 `main` 已明显领先该冻结快照。

---

## 4. 最近关键合并

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

首轮 live gate 发现测试夹具 Skill name 不符合真实 lowercase kebab-case 约束，修正夹具后完整链路全绿；没有降低业务校验。

### PR #34：真实 Chromium MCP Apps Browser Acceptance

PR #34 没有新造一套 Host，而是复用现有产品链路：

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

CI 使用真实 Compose：

```text
PostgreSQL
Backend / local-jwt
Frontend :3456
MCP sandbox :3457
upstream ext-apps map MCP Server
Chromium / Playwright
```

已确认：

- real local-jwt browser session
- MCP Admin register / Health / Discovery
- Skill Binding
- 浏览器 MCP Client 经平台 authenticated Proxy 连接真实 MCP server
- `show-map` tool definition 可发现
- 真实 `ui://` HTML resource 可读取
- Host origin = `http://localhost:3456`
- Sandbox origin = `http://localhost:3457`
- Sandbox 创建 inner iframe
- 真实 MCP App HTML 写入 inner iframe 并可被 Chromium 观察到
- 无 sandbox ready timeout / origin rejection / listTools / readResource fatal error

该 Gate 只把“LLM 产生 ToolCall”这一环固定为确定性 ToolCall fixture；MCP Client、Proxy、MCP server、resource transport、sandbox 与浏览器渲染全部是真实链路。因此它不能代替真实 Provider Tool Calling，但已经足以关闭“浏览器 MCP Apps iframe/sandbox 是否真实工作”的疑问。

### #11 真正剩余

只剩：

1. **真实 Provider 驱动 Agent MCP Tool Call**：模型必须真正选择并执行绑定 MCP Tool，不能用 mock model / 固定 ToolCall fixture 替代。

不要再重复实现或验收 Admin register / Health / Discovery / Binding / Proxy / Apps resource transport / browser sandbox rendering；PR #33 + #34 已覆盖。

---

## 8. Issue 总状态

已关闭/完成基础能力：

- #4 PostgreSQL Persistence ✅
- #5 Session / Memory / A2UI reconstruction ✅
- #6 ObjectStorage / Artifact ✅
- #7 Built-in JWT ✅
- #8 GCP optionalization ✅

保持 OPEN、等待最终真实验收：

- #1 Self-host 全链路
- #2 OpenAI-compatible
- #3 Docker Compose
- #9 target migration + quota/Tool Calling final acceptance
- #10 real Provider E2E
- #11 real Agent MCP Tool Call

---

## 9. 当前 CI Gate

- Tenant isolation
- Tenant live self-host acceptance
- Core runtime persistence
- Self-host baseline
- Self-host auth baseline
- Self-host no-GCP
- MCP admin
- **MCP live self-host acceptance（包含 Chromium separate-origin MCP Apps browser acceptance）**
- Model provider

CI 已覆盖大量 Memory/PostgreSQL、no-GCP、local-jwt、Session/Memory/A2UI、ObjectStorage、Tenant、MCP、Provider routing 等路径。

PR #33 已证明真实 `ext-apps` MCP Server 可以经平台 Admin/Registry/Skill Binding/Proxy 完成 MCP 协议与 HTML resource transport；PR #34 已进一步证明 Chromium 中真实 separate-origin sandbox/iframe 能加载该 MCP Apps HTML。

CI 仍不得冒充真实外部 Provider。没有真实第三方 endpoint / secret 时，不得把固定 ToolCall 或 mock model 当成 #10/#11 最终验收。

---

## 10. 下一步执行顺序

### 第一优先：#10 / #2 真实 Provider E2E

有真实 endpoint + secret 时直接做：

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
Agent final response
```

这一轮可以同时收口：

- #10 real Provider E2E
- #11 real Agent MCP Tool Call
- #9 Tenant quota / Tool Permission / Model Policy 的 LLM-dependent final acceptance
- #2 OpenAI-compatible 全链路验收

### 第二优先：#9 目标部署 legacy migration

需要真实现存 legacy 数据，代码已经准备好；不要重新写 migration tooling。

执行顺序：

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

### 第三优先：其他真实浏览器/产品体验验收

MCP Apps browser rendering 已完成，不要再作为 #11 阻塞项。剩余浏览器方向重点可放在：

- A2UI surface/action
- Skill Studio model selection（配合真实 Provider）
- Chat / AG-UI 完整体验

### 第四优先：发布收口

完成真实验收后推进：

- #12 中文化 / Branding
- #13 GHCR / versioned release
- #14 upstream sync
- #16 S3 adapter
- #17 OIDC extension

---

## 11. 开发约束

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
