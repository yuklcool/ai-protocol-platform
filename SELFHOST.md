# Self-hosting guide

This document describes the current production-style self-host baseline for `ai-protocol-platform`.

The design principle is simple: **use as few infrastructure components as possible**. PostgreSQL is reused for platform data, stable Tenant metadata, built-in accounts, ADK Session and durable Memory. A backend-mounted Docker Volume stores user objects and ADK Artifacts. Redis, MinIO, Keycloak, a separate Session database and a separate Memory database are not required by the default stack.

For versioned prebuilt GHCR images, see [docs/selfhost-release-images.md](./docs/selfhost-release-images.md).

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
  ├── MCP / MCP Apps
  ├── built-in JWT auth ───────┐
  ├── stable Tenant policy ────┤
  ├── ADK Session ─────────────┤
  ├── durable Memory ──────────┼──> PostgreSQL :5432
  ├── platform/tenant data ────┤
  └── auth_users ──────────────┘
  │
  ├── user files ─────────────> /data/objects
  └── ADK Artifacts ──────────> /data/artifacts

mcp-sandbox :3457
  └── separate-origin MCP Apps iframe host
```

Default Docker services:

- frontend
- backend
- PostgreSQL
- MCP Apps sandbox

The production-style Docker path deliberately runs:

```env
SELF_HOSTED_MODE=1
LOCAL_MODE=0
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
AUTH_BACKEND=local-jwt
OBJECT_STORAGE_BACKEND=local
```

`LOCAL_MODE=1` is reserved for the shorter source-development loop and its development substitutes. It is not the normal self-host deployment mode.

## Requirements

A Linux server needs:

- Docker Engine
- Docker Compose v2 (`docker compose`)
- outbound HTTPS access to the configured model provider
- ports 3456, 1956 and 3457 available, or equivalent reverse-proxy mappings

No GCP project, Firebase project, Vertex Agent Engine, Redis, MinIO or Keycloak is required for the baseline.

## Deployment choices

### Versioned GHCR images

This is the preferred operational path after a versioned release is published. Download these assets from the GitHub Release:

```text
docker-compose.release.yml
.env.selfhost.example
```

Then:

```bash
cp .env.selfhost.example .env
# Release assets already pin APP_VERSION to the exact vX.Y.Z tag.
# Configure required secrets/provider values.

docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

The release Compose has no source build contexts and no source-code bind mounts. PostgreSQL migrations are bundled in the backend image and applied before backend startup.

### Build from source

Use this path for development or a custom frontend build:

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
# configure required secrets/provider values

docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

Default local endpoints:

```text
Frontend:         http://localhost:3456
Backend API:      http://localhost:1956/docs
MCP Apps sandbox: http://localhost:3457/sandbox.html
```

## Authentication

The self-host identity selector is:

```env
AUTH_BACKEND=local-jwt   # production-style self-host default
AUTH_BACKEND=stub        # LOCAL_MODE development only
AUTH_BACKEND=firebase    # existing cloud adapter
AUTH_BACKEND=oidc        # optional enterprise OIDC adapter
```

### First administrator

Generate a JWT signing key:

```bash
openssl rand -base64 48
```

Configure:

```env
JWT_SIGNING_KEY=<generated-secret-at-least-32-bytes>
SELFHOST_ADMIN_EMAIL=admin@example.com
SELFHOST_ADMIN_PASSWORD=<strong-password-at-least-12-characters>
```

On the first startup, the backend creates that account with platform-admin access. Later restarts do not overwrite its stored password or roles. Once at least one local account exists, bootstrap email/password values may be removed; the signing key must remain stable unless you intentionally rotate it.

If local-jwt is selected but the signing key is missing/too short, or the first startup has no account and no bootstrap credentials, startup fails loudly.

### Local account storage

Built-in accounts are stored through the Repository abstraction in PostgreSQL. Passwords are salted `scrypt` hashes. The login API never returns password hashes and uses a generic authentication failure response.

### JWT authorization behavior

Relevant settings:

```env
JWT_SIGNING_KEY=...
JWT_PREVIOUS_SIGNING_KEYS=
JWT_ISSUER=ai-protocol-platform
JWT_AUDIENCE=ai-protocol-platform
JWT_EXPIRE_MINUTES=60
```

The current key signs new HS256 access tokens. Prior valid keys can be temporarily listed in `JWT_PREVIOUS_SIGNING_KEYS` during rotation.

Authorization is **server-authoritative**. After token verification, the backend reloads the current account and trusted Tenant/role state from persistence rather than trusting browser-provided tenant/group/role values. Therefore role removal, account disabling and Tenant policy changes take effect independently of stale browser claims.

The built-in browser session stores the bearer token in `sessionStorage`. Closing the tab drops the browser session. On page reload the frontend calls `/api/auth/whoami` to refresh server-authoritative identity state.

## Stable Tenant boundary

The current self-host baseline uses explicit stable `tenant_id` as the authority boundary. Historical domain/client identity remains only as a compatibility/migration layer.

Tenant-aware enforcement covers, among other paths:

- Session and chat metadata
- documents/folders/object namespaces
- MCP server scope
- Admin Audit
- Tool Permission
- Model Policy (`allowedModels/defaultModel`)
- budget/quota extension points

The codebase includes auditable legacy ownership migration tooling and a real Compose/PostgreSQL/local-jwt Tenant A/B isolation gate. That gate deliberately uses the same UID in two different stable tenants to prove the Tenant boundary is not accidentally reduced to user ID.

## Persistence defaults

```env
DATA_BACKEND=postgres
SESSION_BACKEND=postgres
MEMORY_BACKEND=postgres
DATABASE_URL=postgresql://aip:...@postgres:5432/aip
```

One PostgreSQL instance carries the default structured/durable state:

```text
PostgreSQL
├── platform + tenant documents
├── auth_users
├── model/provider + MCP registries
├── ADK Session + events/state
└── durable ADK Memory
```

### Schema migrations

The backend startup path executes:

```text
scripts/apply_selfhost_migrations.py
```

before bootstrap seeding and Uvicorn startup. Applied SQL filenames are recorded in:

```text
platform_schema_migrations
```

The runner is idempotent. Existing source deployments that originally received `001_postgres_documents.sql` through PostgreSQL initdb are compatible: the `CREATE` statements are idempotent, then the migration is journaled.

### Session

`SESSION_BACKEND=postgres` reuses Google ADK's `DatabaseSessionService`. The platform does not maintain a second custom SQL Session implementation.

Existing alternatives remain available:

```env
SESSION_BACKEND=memory
SESSION_BACKEND=vertex
```

### Memory

`PostgresMemoryService` uses the Repository/PostgreSQL layer and persists ADK memory rows without requiring embeddings, Redis or a vector database. Current recall intentionally mirrors simple ADK in-memory semantics with durable keyword/text search, including substring recall for Chinese text.

`MEMORY_SEARCH_SCAN_LIMIT` caps the number of recent per-user rows scanned by a recall. If semantic vector recall is needed later, PostgreSQL + pgvector should be evaluated before adding a separate vector database.

## File / Artifact storage

Default self-host storage:

```env
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=/data/objects
ARTIFACT_BACKEND=local
ADK_ARTIFACT_ROOT=/data/artifacts
```

PostgreSQL stores document metadata while bytes live on the persistent `object-data` volume under trusted Tenant/user namespaces. ADK `FileArtifactService` uses the same persistent volume under `/data/artifacts`.

Local filesystem paths are never returned as public URLs. Preview/download stays behind authenticated FastAPI routes that resolve authorization and object ownership before reading bytes.

Deletion is staged because PostgreSQL and filesystem storage cannot participate in one ACID transaction:

```text
metadata -> deletionStatus=deleting
binary   -> delete
metadata -> delete
```

Failures retain durable recovery state for reconciliation.

`OBJECT_STORAGE_BACKEND=gcs` remains an optional cloud adapter. S3-compatible storage is also available as an opt-in adapter and is not required by the default stack.

Optional S3-compatible configuration:

```env
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_S3_BUCKET=your-bucket
OBJECT_STORAGE_S3_ENDPOINT=https://s3.example.com
OBJECT_STORAGE_S3_REGION=us-east-1
OBJECT_STORAGE_S3_ACCESS_KEY=
OBJECT_STORAGE_S3_SECRET_KEY=
OBJECT_STORAGE_S3_SESSION_TOKEN=
OBJECT_STORAGE_S3_ADDRESSING_STYLE=auto
```

The adapter keeps every object under `tenants/<tenant_id>/`, supports bounded-memory upload/download, list/exists/delete and time-limited presigned GET/PUT URLs. AWS IAM/workload credentials can be used by leaving the explicit key fields empty. Custom S3 endpoints such as Cloudflare R2, MinIO/AIStor, Ceph RGW and Garage can set `OBJECT_STORAGE_S3_ENDPOINT`; many self-hosted endpoints use `OBJECT_STORAGE_S3_ADDRESSING_STYLE=path`. Enabling this adapter does **not** add an S3/MinIO service to the default Compose stack.

## Model providers

The self-host runtime is registry-driven. It supports OpenAI official, Gemini Developer API, Anthropic and generic OpenAI-compatible gateways, with provider-specific base URL and secret reference configuration.

A simple OpenAI-compatible environment path is:

```env
PLATFORM_DEFAULT_MODEL=<registered-model-id>
OPENAI_API_KEY=<provider-key>
OPENAI_API_BASE=https://your-provider.example/v1
```

Dynamic Provider/Model CRUD, completion/tool probes, default/tier mappings and Tenant model policies are available through the current platform control plane. Source-build Self-host enables Skill Studio by default (`ENABLE_SKILL_STUDIO=true`), and release frontend images are built with Skill Studio enabled so administrators can select effective dynamic models from the product UI. See [docs/selfhost-openai-compatible.md](./docs/selfhost-openai-compatible.md).

The remaining acceptance boundary is intentionally strict: #10/#11 are not considered finished until a real non-OpenAI OpenAI-compatible endpoint drives an Agent conversation and actual Tool Calling. Mock/fixed ToolCalls do not replace that final provider E2E.

## MCP / MCP Apps

The self-host baseline includes:

- MCP Server Admin CRUD
- Platform/Tenant scope
- HTTP/SSE/Streamable HTTP transport
- real `initialize` Health
- `tools/list`, `resources/list`, `prompts/list` Discovery
- Skill Binding
- authenticated `/mcp/{server_id}` browser/runtime proxy
- separate-origin MCP Apps sandbox

A real Compose acceptance already covers:

```text
Admin register
  -> Health / initialize
  -> Discovery
  -> Skill Binding
  -> platform MCP Proxy
  -> tools/list + resources/read
  -> real ui:// HTML
```

A Chromium/Playwright gate additionally proves the real `ui://` resource is written into an inner iframe through the separate-origin sandbox. Therefore MCP transport and browser iframe rendering are no longer manual-only acceptance items.

The remaining #11 boundary is a **real model choosing and executing the bound MCP Tool**.

See [docs/selfhost-mcp-server.md](./docs/selfhost-mcp-server.md).

## CI / smoke tests

Basic self-host smoke:

```bash
BACKEND_URL=http://127.0.0.1:1956 \
FRONTEND_URL=http://127.0.0.1:3456 \
SANDBOX_URL=http://127.0.0.1:3457 \
bash scripts/smoke-selfhost.sh
```

Dedicated CI gates currently cover:

- PostgreSQL Repository / Session / Memory / A2UI reconstruction
- local ObjectStorage / Artifact persistence
- local-jwt bootstrap and server-authoritative authorization
- no-GCP startup boundary
- real stable Tenant A/B isolation
- Model Provider registry/routing/policy
- MCP Admin and real MCP protocol transport
- Chromium separate-origin MCP Apps rendering
- source self-host image build and smoke
- versioned self-host release image build pipeline

A release still requires real Provider-dependent acceptance before the overall protocol project can be called fully accepted:

1. normal Agent/Skill conversation against a real configured Provider;
2. real Provider Tool Calling;
3. real model selection/execution of a bound MCP Tool;
4. final Tenant quota / Tool Permission / Model Policy verification on that live model path.

## Versioned release images

The release pipeline builds:

```text
ghcr.io/yuklcool/ai-protocol-platform-backend
ghcr.io/yuklcool/ai-protocol-platform-frontend
ghcr.io/yuklcool/ai-protocol-platform-mcp-sandbox
```

Stable `vX.Y.Z` release tags produce `linux/amd64` and `linux/arm64` manifests plus semver, `latest`, and exact `sha-*` tags. The current production release workflow intentionally rejects prerelease-style tags. BuildKit SBOM/provenance attestations are enabled, and published images are scanned for fixable HIGH/CRITICAL vulnerabilities before the GitHub Release is created.

Before GitHub Release creation, CI also performs an anonymous no-clone cold start in a fresh directory using only the tagged release Compose/env files and public GHCR images. It verifies backend/frontend/sandbox health and a real local-jwt administrator login. The published env asset is generated with `APP_VERSION` already pinned to the exact release tag.

The release frontend image is relocatable: it is compiled with a dedicated sandbox-origin placeholder and replaces that placeholder at container startup from `MCP_SANDBOX_PUBLIC_URL`.

See [docs/selfhost-release-images.md](./docs/selfhost-release-images.md) for exact deployment and rollback commands.

## Reverse proxy / TLS

For an internet-facing server, place Caddy, Nginx, Traefik or another TLS reverse proxy in front of the frontend and sandbox.

The browser-facing frontend and MCP sandbox must remain different origins. Example:

```text
https://ai.example.com  -> frontend:8080
https://mcp.example.com -> mcp-sandbox:8080
```

Configure:

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
```

Use TLS for any internet-facing local-jwt deployment; browser bearer tokens must never traverse an unencrypted public network.

## Backup and rollback

A complete self-host backup needs both:

```text
1. PostgreSQL data
2. object-data volume (/data/objects + /data/artifacts)
```

Keep the JWT signing key in a separate protected secret backup.

For image-based deployment, application rollback is normally performed by restoring the previous `APP_VERSION` and pulling/updating Compose again. Database migrations may be forward-only; image rollback does not replace a database restore when an incompatible schema migration has already been applied.

## Current optional extensions / limitations

- OIDC/Keycloak is implemented as an optional enterprise adapter; production IdPs still require deployment-specific issuer/client configuration and explicit subject mapping.
- local-jwt currently uses access-token-only browser sessions rather than a refresh-token flow.
- S3-compatible ObjectStorage is available as an optional adapter and remains outside the default Compose service set.
- real external Provider Tool Calling acceptance still requires endpoint credentials supplied by the deployment owner.
- internet-facing installations remain responsible for TLS, secret management, backups and normal operational hardening.

The project should not add Redis, MinIO, Keycloak, a dedicated vector database or a queue merely because those components are common in larger deployments. Add optional infrastructure only when a concrete workload requires it.
