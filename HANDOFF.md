# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`
> 上游：`sunholo-data/ai-protocol-platform`
> 状态更新时间：**2026-09-19**
> 当前主线：**真实 Provider / MCP / A2UI action-run 与 v1.0.1 发布已验收；#1/#3/#10/#11/#13 已关闭。当前集中处理 #9 的持久化租户预算、真实租户 LLM 隔离和目标部署迁移。**

---

## 1. 当前结论

基础 Self-host 已完成：PostgreSQL 平台数据 / Session / Memory / A2UI、local JWT、无 GCP 启动、本地文件存储、租户资源隔离、Model/MCP 管理、中文品牌、可选 S3/OIDC、版本化 GHCR 发布。

已确认的真实验收：

- `https://sub2api.yukl.qzz.io/v1` + `gpt-5.6-luna`，凭证使用已配置的 Actions secret `REAL_PROVIDER_API_KEY`，不重复要求用户提供。
- Provider / Dynamic Model / Skill Studio / Chat / Agent MCP `geocode`、`show-map` / MCP Apps / A2UI `surface-action-run`：[2026-09-19 全绿运行](https://github.com/yuklcool/ai-protocol-platform/actions/runs/35414266423)。
- [MCP live 验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/35414266384)。
- [v1.0.1 发布验收](https://github.com/yuklcool/ai-protocol-platform/actions/runs/35355685248)：multi-arch、Trivy、匿名 GHCR pull、no-clone cold-start、Release assets。

#1/#2/#3/#4/#5/#6/#7/#8/#10/#11/#12/#13/#14/#16/#17 已关闭。业务 Issue 只剩 #9；#15 是总 Roadmap。

本轮继续 PR #72（尚未合并）：Repository/PostgreSQL 租户预算执行器、启动注册、source/release Compose 配置；修复拒绝请求占用预算、多次模型调用共用账本 ID、流式 partial 提前结束对账，补 PostgreSQL 重建/A-B 隔离测试。预算回调回归原被 GCP 目录规则跳过，现已启用实际运行。本地 39 项预算测试通过；新增 PostgreSQL 用例须由 CI 验证。

PR #72 原发布 gate 因 AnyIO 4.13.0 的 CVE-2026-63374 失败；本轮更新到修复版本 4.14.2 并保持 Trivy gate，需新提交 CI 确认。

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

PR #54 — Live Skill Studio dynamic model gate
aa65322a1a47dca9e1e8b2910ce3feed43fdb6a1

PR #55 — True no-clone release cold-start gate
7142371830cb7357b87d00b3c3de8ad698757086

PR #56 — Live persisted A2UI surface browser acceptance
de974410e13b82523c455b68b3bfb086ac196016
```

---

## 5. #9 Tenant / Isolation 状态

#9 的资源隔离与迁移工具已完成。持久化预算执行器正在 PR #72 收口，真实目标部署迁移和 LLM-dependent acceptance 尚未完成。

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

## 6. #10 Model Provider 已完成

Provider/Model CRUD、secret reference、探测、effective registry、独立 Provider 路由、默认模型/tier、Tenant model policy、Skill Studio 选择保存及真实 Agent Tool Calling 均已完成。Issue 已关闭。

运行入口与配置见 [真实 Provider 验收说明](docs/real-provider-acceptance.md)。不要重复实现 Provider 系统或把已经完成的真实验收列为缺口。

---

## 7. #11 MCP Server 管理已完成

Admin CRUD、scope、secret redaction、Health/Discovery、Skill Binding、Proxy、Apps HTML transport、独立 origin 浏览器渲染以及真实模型驱动 Tool Calling 均已验证，Issue 已关闭。PR #33/#34 提供协议及浏览器基线；2026-09-19 的真实 Provider gate 已覆盖完整 Agent 链路。

---

## 8. Issue 总状态

- 已完成并关闭：#1–#8、#10–#14、#16、#17。
- #9 OPEN：持久化预算 PR #72 收口、真实 Tenant A/B LLM quota/Tool Permission/Model Policy 验收、目标 legacy 数据迁移。
- #15 OPEN：持续同步的总 Roadmap。

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
- **Model provider Skill Studio live（Compose/PostgreSQL/local-jwt/Chromium 动态模型选择与持久化）**
- **A2UI live self-host acceptance（真实 Chat route + persisted surface + browser action state + PostgreSQL hard-reload recovery）**
- Frontend auth tests
- OIDC Keycloak compatibility（真实 Keycloak discovery/JWKS/signed ID token）
- Self-host release images（source/release Compose、release image build、runtime frontend config）
- Tag-only release gate（anonymous GHCR pull + true no-clone cold-start，首次真实 `vX.Y.Z` 时执行）

CI 已覆盖大量 Memory/PostgreSQL、no-GCP、local-jwt、Session/Memory/A2UI、ObjectStorage、Tenant、MCP、Provider routing 等路径。

PR #33 已证明真实 `ext-apps` MCP Server 可以经平台 Admin/Registry/Skill Binding/Proxy 完成 MCP 协议与 HTML resource transport；PR #34 已进一步证明 Chromium 中真实 separate-origin sandbox/iframe 能加载该 MCP Apps HTML。

PR #56 进一步证明非 LLM 的 A2UI persisted surface/render/action-state/reload 链路真实可用；它刻意不调用 `surface-action-run`，因为该端点会启动真实 Agent/LLM turn。

CI 仍不得冒充真实外部 Provider。没有真实第三方 endpoint / secret 时，不得把固定 ToolCall、seeded A2UI state 或 mock model 当成 #10/#11 及最终 Agent round-trip 验收。

---

## 10. 下一步执行顺序

1. 完成 PR #72 的预算回归、真实 PostgreSQL 账本恢复与发布镜像 Trivy 验证，检查无阻断后合并。
2. 使用已授权的真实 Provider 配置，验证 Tenant A/B 实际调用的预算桶、Tool Permission 与 Model Policy。不能用单租户 Provider gate 或纯账本单测代替。
3. 目标生产 legacy 数据可用后，按 `docs/tenant-ownership-migration.md` 执行 dry-run → review ambiguous ownership → apply → verify → rollback drill。不要重新实现迁移工具，也不要猜历史 ownership。
4. 合并后的新代码不等于已进入 v1.0.1；需要发布时创建新版本，不能移动已有 tag 或冻结部署分支。

预算执行器为显式 opt-in：`BUDGET_ENFORCER=tenant-repository`。Tenant quota 设置 `llmBudgetUsd` / `llmBudgetPeriod` / `llmBudgetSoftThreshold`；Skill 同时配置 budget identity `tenant_id` 与 missing identity `block`。缺少 Skill budget 配置或 exempt Skill 仍按现有协议跳过，不能宣称这是所有 Skill 强制执行的平台额度。未知模型的定价、预估费用与真实账单偏差也须在 LLM 验收时确认。

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
