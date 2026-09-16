# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 状态更新时间：**2026-09-16**  
> 当前主线：**Self-host 基线已完成；#9 多租户等待 legacy ownership + 真实 E2E；#11 MCP 管理面代码已完成、等待真实部署验收；#10 Model Provider 配置中心正在继续实施。**

---

## 1. 当前结论

这个仓库已经不是“只做 Roadmap 的 fork”。当前 `main` 已完成 Self-host 核心底座、多租户核心边界、MCP 管理面和动态模型运行时接入，并有 PostgreSQL / Docker / no-GCP / provider routing 等 CI 回归。

当前平台已具备：

- PostgreSQL Repository / persistence abstraction
- PostgreSQL ADK Session
- PostgreSQL durable Memory
- PostgreSQL 下 A2UI surface / clientDataModel / lastAction 恢复
- Local ObjectStorage + Docker Volume
- ADK `FileArtifactService` 本地持久化
- Built-in local JWT
- 无 GCP 凭证/资源依赖的 Self-host 启动路径
- 显式 `tenant_id` 与 fail-closed tenant boundary
- Tenant-aware MCP Registry / Proxy / Audit / Budget identity
- MCP Server Admin API + Admin UI + Health / Discovery + Skill Binding
- YAML bootstrap + Database dynamic model overlay
- 多 OpenAI-compatible Provider 独立 `base_url / api_key_ref`
- Dynamic Model 实际进入 ADK Agent runtime
- Self-host / Core Runtime / Tenant / MCP / Model Provider 专项 CI Gate

当前不应再把工作重点描述为“建设基础架构”。现在主要是：

1. 完成 #10 Model Provider 配置中心剩余 UI / Model Probe / 默认模型与 tier 管理。
2. 完成 #9 legacy ownership 迁移和 Tenant A/B 真实 E2E。
3. 完成 #11 MCP 管理流程真实自托管 E2E。
4. 用真实浏览器/真实 Provider 完成 #1/#2/#3 最终协议验收并收口。
5. 再推进 #12 中文化、#13 GHCR/版本发布、#14 upstream sync 等后续项。

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
- MCP Apps 继续独立 sandbox/origin
- Google Cloud 能力以 adapter/provider 形式保留，不直接删除
- 新能力尽量放在 Repository / Provider / Adapter / Config 层
- Tenant、认证、权限必须 server-authoritative / fail-closed
- 上游兼容优先，不把 fork 改造成无法同步的完全不同项目

---

## 3. Self-host 默认架构

当前默认栈：

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

默认不要求：

- Redis
- MinIO
- Keycloak
- Firebase
- GCP project / ADC
- 独立 Session DB
- 独立 Memory DB
- 独立消息队列
- 独立向量数据库

---

## 4. 部署分支与 `main` 的关系

### 冻结部署快照

稳定部署分支：

```text
deploy/2026-09-15
```

创建时对应快照 SHA：

```text
e07dbe78da4ec5ba06866ca423707c9eb50d9329
```

**规则：不要移动、重写或把后续 main 自动合并到这个冻结分支。**

需要新的稳定快照时，应创建新的 deploy branch（例如新的日期或 `-r2`），而不是修改 `deploy/2026-09-15`。

当前 `main` 已经包含冻结分支之后的新能力，包括 #19、#20、#21、#23、#24、#25、#26、#27 等后续工作。

### 当前 main 最新关键合并

截至本次交接，最近的模型运行时合并为：

```text
PR #27
merge SHA: aaf1d1de443fcd595da23f21117ddac3493fcd09
```

---

## 5. Issue 总状态

### 已完成 / 已关闭

- #4 PostgreSQL Persistence ✅
- #5 Session / Memory / A2UI reconstruction ✅
- #6 ObjectStorage / Artifact ✅
- #7 Built-in JWT ✅ Closed
- #8 GCP optionalization ✅ Closed

### 主体已完成，等待真实部署 / 协议验收

- #1 Self-host 全链路基线 — OPEN
- #2 通用 OpenAI-compatible — OPEN
- #3 Docker Compose Self-host — OPEN
- #11 MCP Server 管理能力 — OPEN

### 仍有真实开发/迁移工作

- #9 显式 Tenant / 隔离 / legacy ownership — OPEN
- #10 Model Provider 配置中心 — OPEN，当前正在继续实施

---

## 6. #1 / #2 / #3：代码基线已完成，仍需最终验收

### #1 Self-host 全链路基线

已有：

- `scripts/smoke-selfhost.sh`
- Self-host baseline CI
- Self-host no-GCP gate
- PostgreSQL / Session / Memory / A2UI reconstruction regression
- MCP / OpenAI-compatible regression
- local-jwt 登录路径

最终关闭前仍需在真实浏览器/真实部署验证：

1. 普通 Chat
2. Runtime Skill
3. MCP Tool
4. MCP App iframe
5. A2UI surface
6. A2UI action round-trip

### #2 OpenAI-compatible

现在已经不是“只支持一个全局 OpenAI Base URL”的实现。

当前包含两条兼容路径：

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

支持 DeepSeek / Qwen / vLLM / LiteLLM Proxy / OneAPI / NewAPI / 内部兼容网关等通过 OpenAI-compatible provider path 接入。

#2 仍保持 OPEN 的主要原因：需要一个真实的非 OpenAI OpenAI-compatible endpoint 完成 Agent + Tool Calling 最终验收。

### #3 Docker Compose

根目录已有生产式 Self-host Compose：

- postgres
- backend
- frontend
- mcp-sandbox
- health checks
- restart / dependency
- persistent volumes
- local-jwt
- local ObjectStorage / artifacts
- dynamic model registry

辅助命令：

```bash
make docker-up
make docker-down
make docker-restart
make docker-ps
make docker-logs
make selfhost-smoke
```

#3 仍保持 OPEN，原因和 #1 类似：最终浏览器/协议链路需要真实部署验收。

---

## 7. #4～#8 Self-host 基础能力

### #4 PostgreSQL Persistence

结构：

```text
Business code
      ↓
Repository
 ├── PostgreSQL   ← Self-host 默认
 ├── Firestore    ← GCP 兼容
 └── Memory       ← dev/test
```

能力包括：

- `DATA_BACKEND=memory|firestore|postgres`
- PostgreSQL / Firestore / Memory Repository
- tenant-aware Repository boundary
- migration CLI
- PostgreSQL integration CI
- runtime direct-Firestore import audit

### #5 Session / Memory / A2UI

Self-host 默认：

```env
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
```

- Session 使用 Google ADK `DatabaseSessionService`
- Memory 使用 `PostgresMemoryService`
- A2UI surface replay state 持久化在 Session state
- `clientDataModel` / `lastAction` 可在 backend reconstruction 后恢复

### #6 ObjectStorage / Artifact

```env
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ADK_ARTIFACT_ROOT=/data/artifacts
```

本地 `/data` volume 承担默认对象与 Artifact 持久化；GCS 作为 adapter 保留。

### #7 Built-in JWT

- PostgreSQL 本地账号
- scrypt 密码哈希
- JWT signing / verify / expiry / rotation
- first-admin bootstrap
- frontend email/password login
- REST / AG-UI Bearer token

OIDC / Keycloak 仍是可选扩展，不是默认依赖。

### #8 GCP Optionalization

正式 Self-host 在：

```env
SELF_HOSTED_MODE=1
LOCAL_MODE=0
AUTH_BACKEND=local-jwt
```

条件下无需 ADC / Firebase / Vertex / GCS 即可启动主路径。

注意：Python 依赖树可能仍包含 Google SDK；“无 GCP”指**运行时不要求 GCP 配置、凭证和云资源**，不是删除所有 Google 包。

---

## 8. #9 显式 Tenant / 隔离 — OPEN

#9 的运行时主边界已经基本收口，不再是“quota 尚未实现”的状态。

### 已完成

- 稳定 `tenant_id`，domain 只作为兼容 identity mapping
- User / Skill / Session / Document / Folder / Artifact / MCP / Audit tenant scope
- tenant-aware 核心资源默认 fail-closed
- MCP Registry / Proxy / cache tenant partition
- Audit `tenantId / actorTenantId`
- PostgreSQL Session / Memory / A2UI 使用稳定租户上下文
- Local ObjectStorage / Artifact tenant-safe namespace
- tenant budget extension point
- `identity_key: tenant_id`
- `missing_identity_policy: block`
- 同 UID 跨租户 / public ACL 跨租户等安全回归

推荐 tenant budget：

```yaml
tool_configs:
  budget:
    identity_key: tenant_id
    missing_identity_policy: block
    cost_multiplier: 1.0
```

语义：

- 正常 tenant_id → 不同租户进入不同 budget bucket
- tenant_id 缺失 → 在模型调用前阻断
- 不会因为 identity 缺失落入错误共享 bucket
- 未显式设置策略的旧 Skill 仍默认 `skip`，用于兼容历史行为

### 关键合并

```text
PR #18 — Tenant/MCP/Audit/PostgreSQL Self-host 修复
PR #20 — fail-closed tenant budget identity
```

### 剩余工作

不得关闭 #9，直到以下内容完成：

1. 将无可信归属的旧 Audit / user / client / tool 数据迁移到明确 tenant ownership。
2. 完成 legacy `clients/{domain}` → tenant ownership 的生产迁移/回滚说明。
3. 做真实 Tenant A / Tenant B E2E，验证：
   - Session
   - 文件
   - Skill 私有配置
   - MCP
   - Audit
   - quota
   均不可串租户。

迁移前，无可信归属的历史记录继续仅允许 platform admin 访问，不通过邮箱猜测 ownership。

---

## 9. #11 MCP Server 管理 — 代码侧已完成，Issue 保持 OPEN

#11 的管理面功能已经落入 `main`，不需要再创建第二套 MCP 子系统。

### PR #21 — Registry 管理 API

已实现：

- MCP Server CRUD
- Platform / Tenant scope
- HTTP / SSE / Streamable HTTP
- Docker service name / 本地网络 URL
-认证 Header / Secret Reference
- Secret write-only / response redaction / audit redaction
- Registry cache invalidation

### PR #24 — Health + Discovery

已实现：

```text
POST /api/admin/mcp-servers/{server_id}/health
POST /api/admin/mcp-servers/{server_id}/discover
```

能力：

- 真实 MCP `initialize` handshake
- `tools/list`
- `resources/list`
- `prompts/list`
- MCP Apps resource URI summary
- configuration / network / authentication / protocol / schema 错误分类

### PR #23 — Admin UI + Skill Binding + Self-host Example

已实现：

- `/admin/mcp-servers`
- 新增 / 编辑 / 删除
- enable / disable
- Health / Discovery
- MCP Apps capability 展示
- 绑定 / 解绑 Skill
- Runtime / Proxy 对 disabled server fail-closed
- Docker Compose 内部 MCP Server 示例
- `docs/selfhost-mcp-server.md`

### #11 剩余验收

必须在真实 Self-host 部署中完成：

1. UI 新增同机或远程 MCP Server
2. Health 成功
3. Discovery 成功
4. 绑定指定 Skill
5. Agent 发起真实 MCP Tool Call
6. 对支持 MCP Apps 的 Server 验证前端真实资源渲染

因此 #11 **不能仅因为单测/CI 通过而关闭**。

---

## 10. #10 Model Provider 配置中心 — 当前重点

#10 已经从“只有 models.yaml + 环境变量”推进到了“动态 Registry 真正进入 Agent runtime”。

### PR #25 — Provider / Dynamic Model 管理后端

合并 SHA：

```text
6c0523de8166026850779df22a4a4bbad34af993
```

已实现：

- `model_providers` persistence registry
- `model_registry` dynamic model persistence
- Platform Admin Provider CRUD
- Dynamic Model CRUD
- `${ENV_VAR}` Secret Reference
- 明文 API Key 直接拒绝
- Provider `GET /models` connectivity test
- Provider 删除 orphan model 防护
- model tier / context / capabilities / residency
- Audit
- `MODEL_REGISTRY_BACKEND=yaml` 强制 GitOps 模式
- Self-host 默认 database overlay

### PR #26 — Effective Model Registry

合并 SHA：

```text
05709e32a6cb1302e2ac46f332ebd0761ab7942b
```

新增：

```text
backend/config/effective_models.py
```

语义：

```text
models.yaml
   │ bootstrap / GitOps baseline
   ▼
effective registry
   ▲
   │ database overlay
model_registry
```

规则：

- dynamic model 可按 `model_id` overlay YAML entry
- disabled model 不进入 effective registry
- missing/disabled provider 的 orphan model fail-closed
- `/api/models` 返回 YAML + database effective models
- Skill Studio 的模型数据源已经可以看到动态模型
- metadata 增加 `provider_id / supports_vision / source`

### PR #27 — Agent Runtime Provider Routing

合并 SHA：

```text
aaf1d1de443fcd595da23f21117ddac3493fcd09
```

新增：

```text
backend/config/runtime_models.py
```

Agent runtime 现在实际使用 effective registry：

```text
Skill model ref
    ↓
runtime_models
    ↓
effective model entry
    ↓
provider_id
    ↓
model_providers
    ↓
LiteLlm(
  model="openai/<api_name>",
  api_base=<provider baseUrl>,
  api_key=<resolved apiKeyRef>
)
```

重要特性：

- 多个 OpenAI-compatible Provider 可在同一 backend process 共存
- 不通过修改进程全局环境切换 Provider
- Dynamic Provider 使用各自的 `baseUrl / apiKeyRef`
- YAML/legacy model 继续兼容全局 `OPENAI_API_BASE / OPENAI_API_KEY`
- dynamic provider secret 缺失时 fail loudly
- fallback credential check 能识别 dynamic provider secret reference
- reasoning / Responses capability 继续与 provider runtime kwargs 合并

PR #27 验证：

- Model Provider gate ✅
- Core Runtime persistence ✅
- Self-host Baseline ✅
- Self-host Baseline 内 OpenAI-compatible provider routing ✅

---

## 11. #10 Model Providers 管理 UI 与模型探测

本批工作接续 `feat/model-provider-admin-ui`，已同步 2026-09-16 main 的交接文档。
分支最终合并状态以 GitHub PR 为准；不要仅凭本节实现记录推断已合并。

已实现：

- `/admin/model-providers`：Provider / Dynamic Model 新增、编辑、删除、启停；
  Provider connectivity、Model completion、Tool Calling 探测。
- Admin 首页平台管理员入口；租户管理员不读取或管理平台 Provider。
- 仅保存 `${ENV_VAR}` 引用，UI 不接受服务器凭证值作为配置方案。
- 探测向目标 Provider 实际发送 `/chat/completions`；强制 `platform_probe` 工具，
  检查函数名称和 JSON 参数结构，不执行返回的工具。
- 文本探测要求非空文本；畸形 message/tool_calls 不再误报成功或导致 500。
- 区分配置、网络、认证、协议、能力、schema 错误；网络错误不回显上游异常内容。
- reasoning 模型不发送 temperature/max_tokens，改用 max_completion_tokens。
- UI 错误提示、请求期间禁用操作、tier/residency 表单类型修复。
- Model Provider gate 增加前端类型检查、交互测试、local-jwt 生产构建。

本地验证：后端 Model Provider gate **121 passed**；前端管理页与入口
**15 passed**；TypeScript 检查通过。生产构建及远端 CI 结果记录在本批 PR。
这里的探测回归使用受控响应，不能替代真实第三方模型的最终验收。

---

## 12. #10 剩余工作

在管理 UI 与探测接口完成合并后，#10 仍有：

1. 默认模型与 tier mapping 管理 / 可视化。
2. 可选 Tenant 级模型白名单 / Tenant 默认模型。
3. 使用真实非 OpenAI OpenAI-compatible endpoint 完成：
   - Provider test
   - Model completion
   - Skill 选择该 model
   - Agent conversation
   - Tool Calling
4. 最终确认无需修改代码/配置文件即可完成完整 Provider → Model → Skill → Agent 流程。

只有完成上述真实端到端验收后，#10 才应关闭。

---

## 13. Secret / Credential 原则

MCP 和 Model Provider 都必须继续遵守同一原则：

```text
配置层保存 Secret Reference
        ↓
运行时解析
        ↓
只传给实际客户端
```

Model Provider 当前使用：

```text
${ENV_VAR}
```

禁止：

- Admin API 返回 API Key 明文
- Admin UI 回显 API Key 明文
- Audit 记录 Secret 值
- 因 Provider Secret 缺失而静默 fallback 到另一套凭证

未来如果加入正式 Secret Store，应继续保留 `secret_ref` 模型，而不是把 Secret 值变成普通配置字段。

---

## 14. 自托管启动

### 冻结快照测试

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
git checkout deploy/2026-09-15
cp .env.selfhost.example .env
# 配置 JWT / admin / model provider
docker compose up -d --build
```

服务端口：

```text
Frontend      3456
Backend       1956
MCP sandbox   3457
PostgreSQL    5432 (Compose internal / according to mapping)
```

### main 开发版

也可以：

```bash
cp .env.selfhost.example .env
make docker-up
```

但必须知道：`main` 包含冻结部署分支之后的新功能，不等同于 `deploy/2026-09-15`。

---

## 15. 当前 CI / 验证边界

当前已有专项 gate：

- Tenant isolation
- Core runtime persistence
- Self-host no-GCP
- Self-host baseline
- MCP admin gate
- Model provider gate

已覆盖大量自动化验证：

- Repository Memory/PostgreSQL regression
- PostgreSQL Session / Memory reconstruction
- A2UI state reconstruction
- local ObjectStorage / Artifact reconstruction
- tenant boundary
- MCP registry/proxy/admin
- dynamic model effective registry
- dynamic provider runtime routing
- OpenAI-compatible routing
- backend image build
- Self-host image build

**自动化测试不能替代以下真实协议验收：**

1. 浏览器 Chat
2. Runtime Skill
3. 真实 Provider completion
4. 真实 Tool Calling
5. MCP Tool
6. MCP App iframe/resource
7. A2UI surface
8. A2UI action round-trip
9. Tenant A/B 真正跨租户验证

Issue #1/#2/#3/#9/#10/#11 的最终关闭都必须遵守这个边界。

---

## 16. 下一步执行顺序

建议按以下顺序继续，不要重新回头改已稳定的 Self-host 基础架构：

### 第一优先：验证并合并当前 #10 管理 UI / 模型探测

```text
feat/model-provider-admin-ui
    ↓
创建 PR
    ↓
Model Provider gate
Frontend build / Self-host build
    ↓
修复
    ↓
合并 main
```

然后继续：

- default model / tier mapping 管理
- 真实 OpenAI-compatible endpoint E2E

### 第二优先：#9 真实多租户收口

- legacy Audit/user/client/tool ownership migration
- `clients/{domain}` migration / rollback 文档
- Tenant A/B E2E

### 第三优先：#11 真实 MCP 自托管验收

- UI 新增 Server
- Health
- Discovery
- Skill Binding
- Tool Call
- MCP Apps resource rendering

### 第四优先：#1/#2/#3 统一协议验收并关闭

这些 Issue 的剩余内容高度重叠，适合在一次真实 Self-host acceptance 中一起完成。

### 后续

- #12 中文化 / Branding
- #13 GHCR / versioned release
- #14 upstream sync（持续任务）
- #16 S3-compatible optional adapter
- #17 OIDC enterprise extension

---

## 17. 开发约束

1. Self-host 默认依赖越少越好。
2. PostgreSQL 能承担的结构化状态不要拆新数据库。
3. 默认文件持久化继续使用 local volume，不强制 MinIO。
4. Keycloak / OIDC 保持可选，不成为默认部署前置条件。
5. Firebase / GCP 能力保留 adapter，不阻塞无 GCP 启动。
6. Tenant / Auth / Permission 一律 server-authoritative / fail-closed。
7. 不信任前端传入的 tenant / group / role claims。
8. MCP / A2UI / AG-UI 保持标准协议优先。
9. Dynamic Model 不应绕过统一 Registry / runtime resolver。
10. Provider API Key / MCP credential 不允许通过普通 API 明文返回。
11. 不要修改冻结的 `deploy/2026-09-15`；新稳定版本创建新快照分支。
12. 每个阶段结束后同步 Issue + HANDOFF，避免文档和代码再次发生状态漂移。
