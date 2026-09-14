# Self-hosting guide

This document describes the current self-hosted baseline for `ai-protocol-platform`.

The design principle is simple: **use as few infrastructure components as possible**. PostgreSQL is reused for platform data, ADK Session, and durable Memory. A backend-mounted Docker Volume is used for user files and ADK Artifacts. Redis, MinIO, Keycloak, a separate Session database, and a separate Memory database are not part of the default stack.

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
  ├── durable Memory ──┼──> PostgreSQL :5432
  ├── platform data ───┘
  │
  ├── user files ─────────> /data/objects
  └── ADK Artifacts ──────> /data/artifacts

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

No GCP project, Firebase project, Vertex Agent Engine, Redis, MinIO, or Keycloak is required for the current self-host baseline.

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

The default self-host file backend is the backend-mounted `object-data` Docker Volume. No MinIO or S3 service is required.

```env
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ADK_ARTIFACT_ROOT=/data/artifacts
```

The on-volume layout is intentionally separated:

```text
/data
├── objects/
│   └── tenants/<tenant-domain>/users/<uid>/docs/<folder>/<file>
└── artifacts/
    └── ... ADK FileArtifactService managed layout ...
```

User document metadata remains in the configured Repository/PostgreSQL backend. Binary content lives in ObjectStorage. The existing domain/client tenant model is reused as the object namespace; self-hosting does not introduce a second independent tenant identity.

### Uploads and large files

HTTP uploads use Starlette's spooled `UploadFile`. The backend streams the file-like object into ObjectStorage instead of calling `await file.read()` for the complete PDF/Office file. Local storage writes in bounded chunks to a temporary file and atomically replaces the destination after `fsync`. The parser rewinds the upload and copies it to its short-lived parse file in bounded chunks as well.

Downloads/previews are also streamed in chunks.

### Controlled download / preview

Local filesystem URLs are never returned to the browser as a public file URL. File access stays behind authenticated FastAPI routes:

```text
GET /api/documents/{doc_id}/preview
GET /api/documents/{doc_id}/download
```

The route verifies document ownership and tenant metadata before resolving the ObjectStorage object. `preview` uses inline disposition; `download` uses attachment disposition.

### Delete consistency

A delete is deliberately staged because PostgreSQL and filesystem/object storage cannot participate in one ACID transaction:

```text
metadata -> deletionStatus=deleting
binary   -> delete
metadata -> delete
```

If binary deletion fails, the metadata is retained with `deletionStatus=failed` so an operator/retry job still has a durable recovery record. If the binary is gone but final metadata cleanup fails, the route attempts to persist `binary_deleted_metadata_pending`.

### ADK Artifacts

Self-host Artifact persistence reuses ADK's official `FileArtifactService`; the platform does not maintain a second artifact/version implementation. The service root defaults to `/data/artifacts`, so Artifact versions survive backend container reconstruction on the same Docker Volume.

Cloud GCS Artifact behavior remains available through the existing ADK/GCS configuration.

### GCS compatibility

`OBJECT_STORAGE_BACKEND=gcs` uses the same `ObjectStorage` business contract. New objects use a tenant-prefixed layout. Historical GCS documents that predate the abstraction are handled through a read/delete compatibility adapter so existing `gs://bucket/users/...` records remain usable without putting GCS SDK calls back into document routes.

### S3-compatible storage

`OBJECT_STORAGE_BACKEND=s3` is reserved as an optional adapter. It is **not** part of the default Compose stack and MinIO is not deployed automatically. The current locked backend dependency set does not yet include an S3 SDK, so the factory intentionally fails loudly instead of pretending S3 support is complete.

When S3-compatible support is added, it should implement the same `ObjectStorage` contract and remain an optional deployment choice; business document code should not change.

### Backup

A complete self-host backup currently needs both:

```text
1. PostgreSQL data
2. object-data Docker Volume (/data/objects + /data/artifacts)
```

Backing up only PostgreSQL preserves metadata/sessions/memory but not uploaded binaries or ADK Artifacts. Backing up only the Volume preserves bytes but not ownership and conversation metadata.

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

The self-host GitHub Actions workflow additionally verifies:

1. the platform Repository can read/write PostgreSQL;
2. self-host fixture data is seeded;
3. ADK Session survives SessionService reconstruction;
4. durable Memory survives MemoryService reconstruction;
5. A2UI visual replay, client data model, and model-facing action state survive PostgreSQL reconstruction;
6. local ObjectStorage and ADK FileArtifactService survive backend container reconstruction;
7. document upload, preview/download, thumbnail, tenant access checks, and recoverable delete behavior use provider-neutral storage;
8. document folders and Agent document context use the Repository facade rather than requiring Firestore.

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

`LOCAL_MODE` still uses a stub identity. PostgreSQL persistence and durable local files do **not** turn the current baseline into a production authentication system.

The intended minimal production path is:

```text
PostgreSQL
├── users / tenants / roles / permissions
└── FastAPI built-in JWT
```

with standard OIDC/Firebase kept as optional adapters. Keycloak is not a default service. This work is tracked in Issue #7.

## Minimal-component roadmap

```text
Completed baseline
  frontend
  backend
  postgres
  local object/artifact volume
  mcp-sandbox (isolated origin)

Next
  #6 finish optional/provider edges and final acceptance
  #7 built-in JWT + PostgreSQL identity
  #8 remove remaining mandatory GCP assumptions

Optional adapters only when required
  GCS / S3-compatible / Firebase / OIDC / Vertex / pgvector
```

The project should not add Redis, MinIO, Keycloak, a dedicated vector database, or a queue merely because those components are common in larger deployments. Add them only after a concrete workload requires them.
