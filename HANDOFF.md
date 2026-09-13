# ai-protocol-platform 二次开发交接文档

> 仓库：`yuklcool/ai-protocol-platform`  
> 上游：`sunholo-data/ai-protocol-platform`  
> 交接日期：2026-09-13  
> 当前阶段：**研究、架构评估与 Roadmap 拆解已完成；核心改造尚未开始实施。**

---

## 1. 这份文档的目的

这份文档用于把当前已经完成的研究和设计判断交给下一位开发者/Agent，目标是让接手者无需重新从零分析仓库，即可直接继续完成自托管与私有化改造。

请特别注意：

- 当前 fork 已创建并可写。
- 已建立完整 Issue Roadmap（#1～#15）。
- **目前没有完成 PostgreSQL、MinIO、OIDC、Docker Compose、通用 OpenAI-compatible 等代码改造。**
- 本文中标记为“已确认”的内容来自对当前公开仓库源码、配置和设计文档的检查。
- 本文中标记为“建议改造”的内容是后续计划，不应当当作已经实现。

---

## 2. 项目定位

这个项目不是一个单独的 Agent Demo，而是一个较完整的 Agent Application Platform 模板。

当前核心技术链路可以概括为：

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

从“技术架构闭环”看，它已经具备：

- Web 前端
- Chat
- Skill Studio
- Admin
- Tenant / Client 配置
- Google ADK Agent Runtime
- Runtime Skill
- MCP
- MCP Apps
- AG-UI
- A2UI
- A2A
- Session / Artifact
- 多模型路由
- 本地运行模式
- Cloud Run / Cloud Build 生产路径

这也是选择它作为二次开发底座的主要原因。

---

## 3. 开源边界与许可证

### 3.1 已确认

公开仓库根目录使用 **Apache License 2.0**。

因此，从 `yuklcool/ai-protocol-platform` fork 下来的公开代码可以：

- 修改
- 私有部署
- 商业使用
- 再分发
- 做自己的产品
- 增加闭源业务模块

需要继续遵守 Apache-2.0 对 LICENSE / NOTICE / attribution / 修改声明等方面的要求。

### 3.2 什么没有完全公开

需要区分“核心 Agent 平台源码”和“Sunholo 自己完整生产基础设施”。

公开仓库里的核心运行代码是可见的，包括：

```text
frontend/
backend/
cli/
infrastructure/
```

但 Sunholo 自己完整的生产 IaC / Terraform / 环境 bootstrap / 内部 dev-test-prod 部署层并不是全部公开在这个仓库中。

仓库设计文档中明确讨论过：

- 完整 Terraform 位于单独的 private repo
- 计划建立 private `platform-source`
- `deploy/` 作为 private tier
- public `ai-protocol-platform` 作为公开投影

注意：新的 repo topology 文档中仍有 Proposed 状态内容，因此不要把“计划中的最终仓库拆分”误认为当前所有目录已经完全迁移完成。

### 3.3 对本 fork 的影响

**不影响我们自行部署核心平台。**

我们不需要 Sunholo 私有 Terraform 才能运行：

```text
Frontend
FastAPI
Google ADK
Skill
MCP
AG-UI
A2UI
```

后续完全可以使用自己的 Docker Compose / Kubernetes / PostgreSQL / MinIO / OIDC 实现生产环境。

---

## 4. 当前最重要的源码事实

### 4.1 A2UI 是真实实现，不是 README 声明

关键代码：

```text
backend/adk/a2ui.py
```

当前后端使用官方 A2UI Agent SDK，核心类包括：

```python
SendA2uiToClientToolset
BasicCatalog
A2uiSchemaManager
```

当前实现使用 A2UI 0.9，并识别标准消息：

```text
createSurface
updateComponents
updateDataModel
deleteSurface
```

A2UI 结果不是简单塞在 Markdown 中，而是通过 AG-UI tool event / result 路径发送给前端 renderer。

当前还存在多 Surface 概念：

```text
chat
workspace
sidebar
modal
```

以及：

```text
replace
patch
```

更新模式。

后续改造必须尽量保持这一标准链路，不建议自己另造 UI 协议。

---

## 5. MCP / MCP Apps

### 5.1 已确认

项目内有真实 MCP server / MCP integration 代码，不只是文档。

重点路径：

```text
backend/protocols/mcp_server.py
backend/adk/tools.py
infrastructure/mcp-sandbox/
```

MCP Apps 使用独立 sandbox/origin，而不是把任意 HTML 直接注入主站。

这部分是项目的价值点之一，后续自托管改造应该保留：

```text
MCP Server
    ↓
MCP Tool / MCP App
    ↓
Agent
    ↓
AG-UI / A2UI / iframe sandbox
```

### 5.2 后续建议

Issue #11 已计划把 MCP Server 管理做成真正可视化、可自托管的能力，包括：

- Base URL
- local Docker service name
- auth headers
- secret reference
- health check
- tools/resources/prompts discovery
- Tenant 私有 MCP
- Skill 绑定

---

## 6. Runtime Skills

不要把 `.claude/skills` 和运行时 Skill 混淆。

项目里至少存在两类 Skill：

### 开发辅助 Skill

```text
.claude/skills/
```

用于 Coding Agent / repo development。

### 真正运行时 Skill

```text
backend/skills/templates/**/SKILL.md
```

这些才是业务 Agent Runtime 使用的 Skill。

平台 API 存在实际的 Skill invocation / stream 路径，Agent Factory 会根据 SkillConfig 构造 ADK Agent。

后续二开时应继续保留“Skill 是配置/数据而不是每个 Agent 都写一套代码”的设计。

---

## 7. 本地运行与 LOCAL_MODE

### 7.1 已确认

项目支持：

```text
LOCAL_MODE=1
```

目标是让开发者在没有 GCP credentials 的情况下运行核心平台。

主要端口：

```text
Frontend      http://localhost:3456
Backend       http://localhost:1956
MCP Sandbox   http://localhost:3457
```

现有推荐入口：

```bash
make dev-local
```

LOCAL_MODE 下，核心 Agent 路径仍然是真实的：

```text
Next.js
FastAPI
Google ADK
Skill
LLM
AG-UI
A2UI
```

被替换/弱化的是云基础设施，例如：

```text
Firestore       -> in-memory
Firebase Auth   -> stub
ADK Session     -> in-memory
Artifact        -> in-memory
Vertex Search   -> disabled/optional
Cloud Trace     -> disabled
```

### 7.2 下一位接手者的第一项任务

直接执行 Issue #1。

不要先改数据库或认证。

先建立“原始 fork 在本地能跑”的可信基线。

必须至少验证：

1. 普通 Chat
2. Runtime Skill
3. MCP Tool
4. A2UI surface
5. A2UI action round-trip
6. MCP Apps sandbox

并建立 smoke test。

---

## 8. 模型 Provider：当前真实能力与缺口

### 8.1 已确认支持

项目当前模型路由支持：

```text
Gemini
Claude
OpenAI
```

Agent Factory 关键代码：

```text
backend/adk/agent.py
```

OpenAI / Claude 通过 ADK `LiteLlm` wrapper。

当前存在环境变量/部署配置：

```text
OPENAI_API_KEY
OPENAI_API_BASE
```

因此项目本身已经考虑自定义 OpenAI endpoint。

### 8.2 当前主要缺口

当前 `resolve_model()` 仍大量依赖模型名称前缀：

```python
gemini-*
claude-*
gpt-*
o3*
```

例如一个完全兼容 OpenAI API 的模型：

```text
deepseek-chat
```

即使配置：

```yaml
provider: openai
api_name: deepseek-chat
```

也可能因为模型名称不满足 `gpt-*` / `o3*` 判断而无法进入正确分支。

这是 Issue #2 的核心原因。

### 8.3 推荐重构方式

不要继续增加模型名 if/else。

应该让路由以 `ModelEntry.provider` 和 capability 为中心：

```text
ModelEntry
   ├── provider
   ├── api_name
   ├── supports_tools
   ├── supports_reasoning
   ├── supports_responses_api
   ├── supports_vision
   └── ...
```

推荐思想：

```python
entry = entry_for(model_id)

if entry.provider == "google":
    ...
elif entry.provider == "anthropic":
    ...
elif entry.provider == "openai":
    ...
```

不要再使用：

```python
resolved.startswith("gpt-")
```

来代表 provider。

### 8.4 Responses API 注意事项

当前 GPT reasoning 路径会根据 reasoning 参数让 LiteLLM 使用 OpenAI Responses API。

这意味着：

- OpenAI 官方 GPT reasoning model 可使用
- 但很多“OpenAI-compatible”服务只实现 `/v1/chat/completions`
- 它们未必实现 `/v1/responses`

因此 Issue #2 必须把：

```text
supports_responses_api
supports_reasoning
```

变成显式 capability，不能仅凭模型名猜。

---

## 9. 当前多租户模型

### 9.1 已确认

公开版不是完全没有多租户。

它已经存在 application-level multi-tenancy。

当前核心思路是：

```text
一个部署
   │
   ├── Tenant / Client A
   ├── Tenant / Client B
   └── Tenant / Client C
```

目前租户常通过邮箱 domain 映射：

```text
user@company-a.com
       ↓
clients/company-a.com
```

关键能力包括：

```text
enabled_skills
default_skill
documents_bucket
derived_group_tags
```

还存在：

```text
backend/admin/clients.py
```

以及 Tenant admin / admin 相关设计与实现。

还实现了 tenant attribution，例如 OpenTelemetry 中带：

```text
tenant.uid
tenant.auth_mode
tenant.group_id
tenant.uid_hash
```

### 9.2 目前的边界

它更接近：

```text
Application-level Multi-Tenancy
```

而不是：

```text
Tenant A -> 独立容器
Tenant B -> 独立容器
```

也就是说多个 tenant 默认共享同一 FastAPI / ADK Runtime，在业务数据、权限、Skill、Bucket 等层面隔离。

### 9.3 后续目标

Issue #9 将 Tenant 提升为显式一等实体：

```text
tenant_id
```

email domain 只作为 identity mapping，不再是 tenant 本身。

所有核心资源都应该明确 tenant scope：

```text
User
Group
Skill
Session
Artifact
MCP Config
Audit
Model Policy
```

默认 fail-closed。

---

## 10. 当前 Google Cloud 耦合点

虽然 LOCAL_MODE 可以运行，但正式云模式目前明显以 Google Cloud 为主。

主要耦合点：

```text
Firestore
Firebase Auth
Vertex Agent Engine / ADK Session
GCS
Vertex AI Search
Cloud Trace / Cloud Logging
Cloud Run / Cloud Build
```

后续不建议“删除 GCP 支持”。

正确方向是抽象为 Provider / Adapter：

```text
DB
├── Firestore
├── PostgreSQL
└── Memory

Auth
├── Firebase
├── OIDC / Keycloak
├── JWT
└── Local Stub

Object Storage
├── GCS
├── S3 / MinIO
└── Local

Session
├── Vertex / ADK cloud
├── PostgreSQL
└── Memory
```

这样可以同时做到：

- 保持上游兼容
- 保留 Google Cloud 用户
- 新增真正自托管能力

对应 Issues：#4～#8。

---

## 11. Docker / 快速部署现状

### 11.1 已确认

当前仓库已经存在多个 Dockerfile，例如：

```text
frontend/Dockerfile
backend/Dockerfile
infrastructure/mcp-sandbox/Dockerfile
```

但当前没有把自托管作为第一目标的一套完整 `docker-compose.yml` 体验。

### 11.2 目标

Issue #3 目标是实现：

```bash
cp .env.selfhost.example .env
docker compose up -d
```

最初版本只需要先把现有 LOCAL_MODE 容器化跑通：

```text
frontend
backend
mcp-sandbox
```

后续随着 #4 / #6 / #7 完成，再逐步加入：

```text
postgres
minio
keycloak
```

不要第一版 Compose 就把所有替代基础设施一次塞进去。

---

## 12. 已建立的 Issue Roadmap

### Phase 0

- #1 验证 LOCAL_MODE 全链路并建立自托管基线

### Phase 1

- #2 将模型路由改造成真正通用的 OpenAI-compatible Provider
- #3 增加 Docker Compose 一键自托管部署

### Phase 2

- #4 抽象数据持久化层并新增 PostgreSQL 实现
- #5 抽象 Session / Memory 层，支持本地持久化后端
- #6 抽象对象存储层并支持 MinIO / S3
- #7 抽象认证层并支持 JWT / OIDC / Keycloak
- #8 将 GCP 专属能力改为可选插件，确保无 GCP 环境可完整启动

### Phase 3

- #9 加强自托管多租户：显式 Tenant ID、隔离策略与配额边界
- #10 增加模型 Provider 配置中心，支持 Base URL / API Key / Model 动态管理
- #11 完善 MCP Server 配置与自托管管理能力

### Phase 4

- #12 增加中文国际化与品牌可配置能力
- #13 增加 GHCR 镜像发布、版本化与自托管 CI/CD
- #14 建立上游同步策略，减少 Fork 长期分叉成本

### 总 Roadmap

- #15 `ai-protocol-platform 自托管与私有化改造总计划`

---

## 13. 推荐实施顺序

不要并行大规模重写。

推荐顺序：

```text
#1
 ↓
#2 ───→ #3
 ↓       ↓
#4 ───→ #5
 ├────→ #6
 └────→ #7
          ↓
         #8
          ↓
         #9
        ↙  ↘
      #10  #11
        \   /
         #12
          ↓
         #13

#14 从现在开始就执行维护原则
```

第一阶段必须只聚焦：

```text
#1 + #2 + #3
```

完成后应先发布一个“可自托管早期版本”，再开始数据库和认证层改造。

---

## 14. 接手者第一天应该做什么

### Step 1：不要改代码，先 clone 并记录当前 commit

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
git remote -v
```

建议额外添加上游：

```bash
git remote add upstream https://github.com/sunholo-data/ai-protocol-platform.git
git fetch upstream
```

### Step 2：读取这些文件

优先阅读：

```text
README.md
HANDOFF.md
backend/.env.example
backend/adk/agent.py
backend/adk/a2ui.py
backend/config/models.yaml
backend/config/models.py
backend/protocols/mcp_server.py
backend/db/clients.py
backend/admin/clients.py
frontend/src/app/
infrastructure/mcp-sandbox/
```

### Step 3：执行 Issue #1

目标：先证明原始平台真实可运行。

重点记录：

- Python / Node 版本
- 必须安装的依赖
- 最小 LLM env
- `make dev-local` 的真实日志
- 三个端口健康状态
- Chat 是否成功
- Tool Call 是否成功
- A2UI 是否成功
- action round-trip 是否成功
- MCP Apps 是否真实渲染还是 fallback

### Step 4：建立 smoke test

后面的每个 PR 都必须跑：

```text
Chat
Skill
Tool
MCP
AG-UI
A2UI
```

否则无法判断去 GCP 化是否破坏核心协议链。

---

## 15. Issue #2 实现提示

这是第一个真正的代码改造，优先级很高。

核心文件：

```text
backend/adk/agent.py
backend/config/models.py
backend/config/models.yaml
```

建议目标结构：

```python
class ModelEntry:
    id
    api_name
    provider
    tier
    capabilities
```

能力不要由名称推断：

```yaml
capabilities:
  tools: true
  vision: false
  reasoning: false
  responses_api: false
```

支持：

```text
OpenAI official
DeepSeek
Qwen
vLLM
LiteLLM Proxy
OneAPI / NewAPI
其他 OpenAI-compatible gateway
```

第一版至少验证两个 endpoint：

1. OpenAI 官方或兼容 GPT 名称
2. 一个非 `gpt-*` 名称（例如 `deepseek-chat`）

只有第二个成功，才说明真正消除了模型前缀硬编码。

---

## 16. Issue #3 实现提示

第一版 Compose 应保持简单：

```text
compose
├── frontend
├── backend
└── mcp-sandbox
```

使用现有 LOCAL_MODE。

不要一开始同时加入：

```text
PostgreSQL
MinIO
Keycloak
Redis
```

这些属于后续 Phase 2。

验收方式：

```bash
docker compose up -d
```

然后浏览器完成一轮真实 Agent + A2UI 请求。

---

## 17. 长期架构原则

### 原则 1：Provider / Adapter，而不是删除原实现

错误做法：

```text
删掉 Firestore
删掉 Firebase
删掉 GCS
```

推荐：

```text
Interface
  ├── Google implementation
  └── Self-host implementation
```

### 原则 2：标准协议链尽量不改

重点保留：

```text
AG-UI
A2UI
MCP
MCP Apps
A2A
```

二开优先发生在 Provider、Persistence、Auth、配置 UI 层。

### 原则 3：Tenant 默认 fail-closed

任何查询如果缺 tenant context，不允许默认为“查全部”。

尤其：

```text
Session
Artifact
Document
Skill private config
MCP secret
Audit
```

### 原则 4：Secret 绝不回显

后续 #10 / #11 需要存：

```text
LLM API Key
MCP auth token
```

必须：

- 加密存储或 Secret backend
- 前端只显示 masked state
- API 不返回明文
- audit 不记录明文

### 原则 5：上游可合并性优先

不要为了改品牌或本地部署把上游核心代码散改几百处。

优先增加：

```text
provider/
adapter/
config/
branding/
i18n/
```

尽量减少长期 merge conflict。

---

## 18. 已确认的几个风险

### 风险 A：公开仓库不是 Sunholo 生产环境 1:1 复制

不要试图复原他们私有 Terraform。

我们的目标是建立自己的 self-host deploy tier。

### 风险 B：LOCAL_MODE 成功不代表生产持久化完成

LOCAL_MODE 很多资源是内存实现。

服务重启后：

- Session
- Artifact
- Tenant 配置

可能不满足生产要求。

因此 #4～#8 是真正生产自托管的关键。

### 风险 C：OpenAI-compatible 不等于 OpenAI Responses-compatible

很多网关只实现：

```text
/v1/chat/completions
```

不要默认它们支持：

```text
/v1/responses
```

### 风险 D：多租户目前主要是应用层隔离

如果未来业务要求：

```text
租户独立进程
租户独立容器
租户独立网络
```

那是另一层基础设施隔离，不属于当前 #9 的第一阶段目标。

### 风险 E：MCP Apps sandbox 必须保持安全边界

不要为了方便把动态 MCP UI 直接改成主站内任意 HTML 执行。

---

## 19. 当前未完成工作清单

截至交接时，以下内容**都还没有实现代码**：

- [ ] LOCAL_MODE 基线实跑与 smoke test
- [ ] 通用 OpenAI-compatible provider
- [ ] capability-driven model routing
- [ ] Docker Compose
- [ ] PostgreSQL adapter
- [ ] persistent Session / Memory backend
- [ ] MinIO / S3 adapter
- [ ] JWT / OIDC / Keycloak
- [ ] no-GCP production mode
- [ ] explicit tenant_id
- [ ] Model Provider Admin UI
- [ ] MCP Admin UI
- [ ] 中文 i18n
- [ ] branding configuration
- [ ] GHCR release pipeline
- [ ] upstream sync automation

也就是说，下一位接手者应从 **Issue #1** 开始，而不是假设这些内容已经完成。

---

## 20. 最终目标架构

长期目标：

```text
                         Web Frontend
                              │
                      AG-UI / A2UI
                              │
                              ▼
                       FastAPI Backend
                              │
                         Google ADK
                              │
             ┌────────────────┼────────────────┐
             │                │                │
           Skills            MCP              A2A
             │                │
             └────────────────┴───────────────┐
                                              │
                              Provider / Adapter Layer
                                              │
          ┌───────────────────┬───────────────┬──────────────────┐
          │                   │               │                  │
          ▼                   ▼               ▼                  ▼
        Model               Data            Auth               Storage
  Gemini/OpenAI/etc   Firestore/Postgres Firebase/OIDC     GCS/S3/MinIO
          │                   │               │                  │
          └───────────────────┴───────────────┴──────────────────┘
                              │
                            Tenant
                              │
                       tenant-aware / fail-closed
```

部署目标：

```text
Docker Compose
      或
Kubernetes
```

并继续兼容 Google Cloud 作为其中一种 deployment/provider option，而不是唯一运行方式。

---

## 21. 继续工作的入口

优先阅读：

- Issue #15：总 Roadmap
- Issue #1：当前第一任务
- Issue #2：第一项架构改造
- Issue #3：第一版可发布自托管能力

工作原则：

> 先证明原版可运行，再做最小改造；每次改造必须有 smoke test；优先扩展而不是重写；保持 A2UI / AG-UI / MCP 标准链路；所有自托管能力通过 provider/adapter 逐步替换 GCP 强依赖。
