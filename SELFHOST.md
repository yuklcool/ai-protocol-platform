# Self-hosting guide

This document describes the current self-hosted baseline for `ai-protocol-platform`.

The design principle is simple: **use as few infrastructure components as possible**. PostgreSQL is reused for platform data, ADK Session, durable Memory, and built-in account records. A backend-mounted Docker Volume is used for user files and ADK Artifacts. Redis, MinIO, Keycloak, a separate Session database, and a separate Memory database are not part of the default stack.

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
  ├── built-in JWT auth ───────┐
  ├── ADK Session ─────────────┤
  ├── durable Memory ──────────┼──> PostgreSQL :5432
  ├── platform/domain data ────┤
  └── auth_users ──────────────┘
  │
  ├── user files ─────────────> /data/objects
  └── ADK Artifacts ──────────> /data/artifacts

mcp-sandbox :3457
  └── separate-origin iframe host
```

Default Docker services:

- frontend
- backend
- PostgreSQL
- MCP Apps sandbox (kept separate because MCP Apps require an isolated browser origin)

The backend still sets `LOCAL_MODE=1` in the current Compose baseline to disable implicit GCP/Firebase/Vertex assumptions. **That no longer means authentication must use the insecure LOCAL_MODE stub.** The checked-in `.env.selfhost.example` selects `AUTH_BACKEND=local-jwt`, so normal self-host deployment uses PostgreSQL-backed accounts and signed JWTs while retaining the no-GCP runtime boundary.

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

### 1. Configure built-in authentication

Generate a random signing key:

```bash
openssl rand -base64 48
```

Put it in `.env` and configure the first platform administrator:

```env
AUTH_BACKEND=local-jwt
JWT_SIGNING_KEY=<generated-secret-at-least-32-bytes>
SELFHOST_ADMIN_EMAIL=admin@example.com
SELFHOST_ADMIN_PASSWORD=<strong-password-at-least-12-characters>
```

On the first startup, the backend creates that account with the platform-admin role. Later restarts never overwrite its stored password or roles. Once at least one local account exists, the bootstrap email/password can be removed from `.env`; the signing key must remain stable or existing access tokens will become invalid.

If local-jwt is selected but the signing key is missing/too short, or the first startup has no account and no bootstrap credentials, startup fails loudly instead of exposing a half-configured deployment.

### 2. Configure at least one model provider

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

### 3. Start

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

Open the frontend and use **Sign in** with the bootstrap administrator credentials. The browser calls the backend through the existing Next.js `/api/proxy` route; no extra public auth service or CORS origin is required.

## Authentication

The self-host identity selector is:

```env
AUTH_BACKEND=local-jwt   # default in .env.selfhost.example
AUTH_BACKEND=stub        # LOCAL_MODE development only
AUTH_BACKEND=firebase    # existing cloud adapter
AUTH_BACKEND=oidc        # reserved optional adapter; currently fail-closed
```

Business routes continue to depend on the same `get_current_user` contract, so Skill permissions, tenant-admin checks, session access rules and audit code do not need provider-specific branches.

### Local account storage

Built-in accounts are stored through the normal Repository abstraction in the `auth_users` collection. With the self-host defaults this means PostgreSQL; no second auth database is introduced.

Passwords are stored as salted `scrypt` hashes. The login endpoint never returns the password hash and returns a generic failure message for bad credentials.

### JWT behavior

Relevant settings:

```env
JWT_SIGNING_KEY=...
JWT_PREVIOUS_SIGNING_KEYS=
JWT_ISSUER=ai-protocol-platform
JWT_AUDIENCE=ai-protocol-platform
JWT_EXPIRE_MINUTES=60
```

The current key signs new HS256 access tokens. `JWT_PREVIOUS_SIGNING_KEYS` can temporarily list prior keys during rotation so already-issued tokens continue to verify until their natural expiry.

The token carries only the minimum identity required to locate the account. Authorization is **server-authoritative**: after signature verification the backend re-loads the current account record from Repository/PostgreSQL and rebuilds domain/group/role data. Therefore:

- removing a role takes effect without waiting for token refresh;
- disabling/deleting an account invalidates an otherwise unexpired token;
- browser-supplied role/tenant claims are not trusted;
- existing `aitana-admin` and `tenant-admin:{domain}` checks remain the permission source until #9 introduces explicit tenant IDs.

### Browser session

The built-in browser session currently stores the bearer token in `sessionStorage`. Closing the tab drops the session. On page reload the frontend calls `/api/auth/whoami`, so the user displayed in the browser is refreshed from the server-authoritative account record.

The shared bearer-token seam used by `fetchWithAuth` and the AG-UI token subscription understands local-jwt, so existing REST, streaming and agent calls do not require per-call-site auth rewrites.

## Persistence defaults

The Docker self-host path defaults to:

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
DATABASE_URL=postgresql://aip:...@postgres:5432/aip
```

One PostgreSQL instance therefore carries the default structured/durable state:

```text
PostgreSQL
├── platform/domain documents
├── built-in auth_users
├── ADK Session + events/state
└── durable ADK Memory
```

### Session

`SESSION_BACKEND=postgres` reuses Google ADK's own `DatabaseSessionService`. The platform does not maintain a second custom SQL Session implementation.

Existing alternatives remain available:

```env
SESSION_BACKEND=memory
SESSION_BACKEND=vertex
```

### Memory

The fork supplies `PostgresMemoryService` using the existing Repository/PostgreSQL layer. Its current behavior deliberately mirrors the simple semantics of ADK's in-memory memory service:

- stores ADK events durably;
- scopes memory by application + user;
- survives backend/service reconstruction;
- supports keyword/text recall, including substring recall for Chinese text;
- does not require embeddings, Redis, or a vector database.

`MEMORY_SEARCH_SCAN_LIMIT` caps the number of recent per-user rows scanned by a recall. If semantic vector recall is needed later, PostgreSQL + pgvector should be evaluated before adding a dedicated vector database.

Existing alternatives remain available:

```env
MEMORY_BACKEND=memory
MEMORY_BACKEND=vertex
```

### Source-only local development

`make dev-local` may continue using memory backends and the LOCAL_MODE stub for the shortest developer loop. The Docker Self-host path is different: the checked-in Self-host env template selects PostgreSQL persistence and local-jwt authentication.

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

User document metadata remains in the configured Repository/PostgreSQL backend. Binary content lives in ObjectStorage. The existing domain/client tenant model is reused as the object namespace; explicit tenant IDs are tracked in #9.

### Uploads and large files

HTTP uploads use Starlette's spooled `UploadFile`. The backend streams the file-like object into ObjectStorage instead of reading the complete PDF/Office file into Python bytes. Local storage writes in bounded chunks to a temporary file and atomically replaces the destination after `fsync`. Downloads/previews are streamed in chunks as well.

### Controlled download / preview

Local filesystem URLs are never returned to the browser as a public file URL. File access stays behind authenticated FastAPI routes:

```text
GET /api/documents/{doc_id}/preview
GET /api/documents/{doc_id}/download
```

The route verifies ownership/tenant metadata before resolving the ObjectStorage object.

### Delete consistency

A delete is staged because PostgreSQL and filesystem/object storage cannot participate in one ACID transaction:

```text
metadata -> deletionStatus=deleting
binary   -> delete
metadata -> delete
```

Failures retain a durable recovery status so an operator/retry job can reconcile the metadata and binary state.

### ADK Artifacts

Self-host Artifact persistence reuses ADK's official `FileArtifactService` rooted at `/data/artifacts`, so versions survive backend container reconstruction on the same Docker Volume.

### GCS compatibility

`OBJECT_STORAGE_BACKEND=gcs` uses the same `ObjectStorage` business contract. Historical GCS documents are handled through a compatibility adapter so cloud users do not need GCS SDK calls in normal document routes.

### S3-compatible storage

`OBJECT_STORAGE_BACKEND=s3` is reserved as optional Issue #16. It is **not** part of the default Compose stack and MinIO is not deployed automatically.

## Backup

A complete self-host backup needs both:

```text
1. PostgreSQL data
2. object-data Docker Volume (/data/objects + /data/artifacts)
```

PostgreSQL now includes account records in addition to domain metadata, sessions and memory. Losing the database therefore also loses the built-in user identities.

Keep the JWT signing key in a separate protected secret backup. It is deliberately not stored in PostgreSQL.

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

The same mechanism works for Qwen, vLLM-served models, LiteLLM Proxy, OneAPI/NewAPI, and internal OpenAI-compatible gateways.

## CI / smoke tests

Basic Self-host smoke:

```bash
BACKEND_URL=http://127.0.0.1:1956 \
FRONTEND_URL=http://127.0.0.1:3456 \
SANDBOX_URL=http://127.0.0.1:3457 \
bash scripts/smoke-selfhost.sh
```

The persistence baseline verifies Repository/PostgreSQL, Session/Memory reconstruction, A2UI replay/state, ObjectStorage/Artifact persistence and image builds.

The dedicated **Self-host auth baseline** additionally verifies:

1. local JWT password/hash/token unit contract;
2. real PostgreSQL first-admin bootstrap;
3. password authentication → JWT issue → JWT verification;
4. server-authoritative role changes on an already-issued token;
5. idempotent bootstrap that does not reset existing credentials;
6. frontend build/typecheck with `NEXT_PUBLIC_AUTH_MODE=local-jwt`.

Before treating a release as fully accepted, still manually verify the real protocol path:

1. a normal Chat turn;
2. a Runtime Skill turn;
3. `Workspace Demo` renders an A2UI surface;
4. an A2UI action reaches the Agent and produces a follow-up result;
5. at least one MCP Tool executes;
6. at least one MCP App renders inside the separate sandbox origin.

Those manual protocol checks remain tracked by #1/#3 and are not equivalent to persistence/auth unit tests.

## Reverse proxy / TLS

For an internet-facing server, place Caddy, Nginx, Traefik, or another TLS reverse proxy in front of the frontend.

The browser-facing frontend and MCP sandbox should remain different origins. Example:

```text
https://ai.example.com  -> frontend:8080
https://mcp.example.com -> mcp-sandbox:8080
```

When changing origins, update the frontend build arguments and sandbox `ALLOWED_HOST_ORIGINS` as well.

Use TLS for any internet-facing local-jwt deployment; the browser bearer token must never cross an unencrypted public network.

## Security boundary

The minimal Self-host authentication boundary is now:

```text
PostgreSQL
├── auth_users
├── domain/tenant metadata
├── roles/group tags
└── permissions

FastAPI
├── scrypt credential verification
├── JWT issue/verify
└── server-authoritative User / AccessContext
```

Firebase remains a compatible provider. Generic OIDC/Keycloak remains an optional enterprise extension and is intentionally **not** a default service.

Current limitations to keep explicit:

- explicit tenant IDs are still #9; local-jwt currently reuses the existing domain-based tenant model;
- OIDC is not implemented yet and `AUTH_BACKEND=oidc` fails closed;
- local-jwt currently uses access-token-only browser sessions rather than a refresh-token flow;
- internet-facing deployments must provide TLS/reverse-proxy hardening and normal operational secret management.

## Minimal-component roadmap

```text
Completed core baseline
  frontend
  backend
  postgres
  built-in local JWT
  local object/artifact volume
  mcp-sandbox (isolated origin)

Next
  #8 remove remaining mandatory GCP assumptions
  close #1/#2/#3 final protocol/provider/deployment acceptance
  #9 explicit Tenant model
  #10 Model Provider UI
  #11 MCP Server UI

Optional adapters only when required
  GCS / S3-compatible / Firebase / OIDC / Vertex / pgvector
```

The project should not add Redis, MinIO, Keycloak, a dedicated vector database, or a queue merely because those components are common in larger deployments. Add them only after a concrete workload requires them.
