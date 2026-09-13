# Self-hosting guide

This document describes the current self-hosted baseline for `ai-protocol-platform`.

The design principle is simple: **use as few infrastructure components as possible**. PostgreSQL is reused for platform data, ADK Session, and durable Memory. Redis, MinIO, Keycloak, a separate Session database, and a separate Memory database are not part of the default stack.

## What runs

```text
Browser
  │
  ▼
frontend :3456
  │  Next.js proxy
  ▼
backend :1956
  │
  ├── Google ADK
  ├── Runtime Skills
  ├── AG-UI / A2UI
  ├── MCP
  ├── MCP Apps integration
  ├── ADK Session ─────┐
  └── durable Memory ──┼──> PostgreSQL :5432
                       │
platform persistence ──┘

mcp-sandbox :3457
  └── separate-origin iframe host
```

Default Docker services:

- frontend
- backend
- PostgreSQL
- MCP Apps sandbox (kept separate because MCP Apps require an isolated browser origin)

The backend still uses `LOCAL_MODE=1` for the current stub-auth / no-GCP development boundary, but durable self-host persistence is no longer in-memory by default.

## Requirements

A Linux server needs:

- Docker Engine
- Docker Compose v2 (`docker compose`)
- outbound HTTPS access to the configured model provider
- ports 3456, 1956 and 3457 available, or equivalent reverse-proxy mappings

No GCP project, Firebase project, Vertex Agent Engine, Redis, MinIO, or Keycloak is required for the current baseline.

## Quick start

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
```

Configure at least one model provider in `.env`.

Gemini Express Mode:

```env
GEMINI_API_KEY=your-key
```

OpenAI:

```env
OPENAI_API_KEY=your-key
OPENAI_API_BASE=https://api.openai.com/v1
```

Any OpenAI-compatible endpoint:

```env
OPENAI_API_KEY=your-key-or-local-placeholder
OPENAI_API_BASE=http://model-gateway.example:8000/v1
```

Then start:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

Endpoints:

```text
Frontend:         http://SERVER_IP:3456
Backend API:      http://SERVER_IP:1956/docs
MCP Apps sandbox: http://SERVER_IP:3457/sandbox.html
```

## Persistence defaults

The Docker self-host path defaults to:

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
DATABASE_URL=postgresql://aip:...@postgres:5432/aip
```

One PostgreSQL instance therefore carries three responsibilities:

```text
PostgreSQL
├── platform/domain documents
├── ADK Session + events/state
└── durable ADK Memory
```

### Session

`SESSION_BACKEND=postgres` reuses Google ADK's own `DatabaseSessionService`. The platform does not maintain a second custom SQL Session implementation.

The configured PostgreSQL URL is normalized to the async SQLAlchemy/asyncpg form required by ADK. Existing alternatives remain available:

```env
SESSION_BACKEND=memory
SESSION_BACKEND=vertex
```

### Memory

Google ADK 1.31.1 does not provide a generic SQL MemoryService, so this fork supplies a small `PostgresMemoryService` using the platform's existing Repository/PostgreSQL layer.

Its current behavior deliberately mirrors the simple semantics of ADK's in-memory memory service:

- stores ADK events durably;
- scopes memory by application + user;
- survives backend restart/service reconstruction;
- supports keyword/text recall, including substring recall for Chinese text;
- does not require embeddings, Redis, or a vector database.

`MEMORY_SEARCH_SCAN_LIMIT` caps the number of recent per-user rows scanned by a recall. If semantic vector recall is needed later, PostgreSQL + pgvector should be evaluated before adding a dedicated vector database.

Existing alternatives remain available:

```env
MEMORY_BACKEND=memory
MEMORY_BACKEND=vertex
```

### Source-only local development

`make dev-local` may continue using memory backends for the shortest developer loop. To explicitly request that behavior:

```env
DATA_BACKEND=memory
SESSION_BACKEND=memory
MEMORY_BACKEND=memory
```

The Docker self-host baseline is different: it defaults to PostgreSQL so a backend restart does not discard sessions and memory.

## File / Artifact storage

The minimal-component roadmap uses a backend-mounted persistent local volume as the default file store, with S3-compatible storage optional later. That work is tracked separately in Issue #6.

At the current implementation stage, GCS compatibility and the existing in-memory artifact fallback remain present. Do not yet treat Artifact/file persistence as completed merely because Session/Memory are durable.

## OpenAI-compatible model registry

Provider routing is registry-driven. An OpenAI-compatible model name does not need to begin with `gpt-`.

Example registry entry:

```yaml
models:
  deepseek-v3:
    api_name: "deepseek-chat"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: global
    context_window: 128000
    max_output_tokens: 8192
    description: "DeepSeek through an OpenAI-compatible endpoint"
```

Then configure a Skill with:

```yaml
model: deepseek-v3
```

The same mechanism works for Qwen, vLLM-served models, LiteLLM Proxy, OneAPI/NewAPI, and internal OpenAI-compatible gateways.

## Smoke / persistence tests

Basic self-host smoke:

```bash
BACKEND_URL=http://127.0.0.1:1956 \
FRONTEND_URL=http://127.0.0.1:3456 \
SANDBOX_URL=http://127.0.0.1:3457 \
bash scripts/smoke-selfhost.sh
```

The self-host GitHub Actions workflow additionally starts a real PostgreSQL container and verifies that:

1. the platform Repository can read/write PostgreSQL;
2. self-host fixture data is seeded;
3. an ADK Session is created and receives an event;
4. the SessionService is reconstructed and the same session/event is restored;
5. Memory is persisted;
6. the MemoryService is reconstructed and still recalls the stored content.

Before treating a release as fully accepted, manually verify the real protocol path as well:

1. a normal Chat turn;
2. a Runtime Skill turn;
3. `Workspace Demo` renders an A2UI surface;
4. an A2UI action reaches the Agent and produces a follow-up result;
5. at least one MCP Tool executes;
6. at least one MCP App renders inside the separate sandbox origin.

## Reverse proxy / TLS

For an internet-facing server, place Caddy, Nginx, Traefik, or another TLS reverse proxy in front of the frontend.

The browser-facing frontend and MCP sandbox should remain different origins. Example:

```text
https://ai.example.com  -> frontend:8080
https://mcp.example.com -> mcp-sandbox:8080
```

When changing origins, update the frontend build arguments and sandbox `ALLOWED_HOST_ORIGINS` as well.

## Security boundary

`LOCAL_MODE` still uses a stub identity. PostgreSQL persistence does **not** turn the current baseline into a production authentication system.

The intended minimal production path is:

```text
PostgreSQL
├── users / tenants / roles / permissions
└── FastAPI built-in JWT
```

with standard OIDC/Firebase kept as optional adapters. Keycloak is not a default service. This work is tracked in Issue #7.

## Minimal-component roadmap

```text
Current
  frontend
  backend
  postgres
  mcp-sandbox (isolated origin)

Next
  #5 finish Session/Memory recovery semantics
  #6 LocalStorage + persistent file volume
  #7 built-in JWT + PostgreSQL identity
  #8 remove remaining mandatory GCP assumptions

Optional adapters only when required
  GCS / S3-compatible / Firebase / OIDC / Vertex / pgvector
```

The project should not add Redis, MinIO, Keycloak, a dedicated vector database, or a queue merely because those components are common in larger deployments. Add them only after a concrete workload requires them.
