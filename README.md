# AI Protocol Platform

Open-source Agent Application Platform built on Google ADK with **Skills + AG-UI + A2UI + MCP + MCP Apps + A2A**.

This fork is being evolved toward a production-friendly, self-hostable platform while preserving the upstream protocol architecture. The implementation roadmap and architectural decisions are documented in [HANDOFF.md](./HANDOFF.md).

## Architecture

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
        ├── MCP / MCP Apps
        ├── A2UI
        └── A2A
```

## Docker Compose quick start

The production-style self-host baseline runs four services:

```text
frontend      :3456
backend       :1956
postgres      :5432 (internal by default)
mcp-sandbox   :3457
```

### Option A — versioned GHCR images (recommended for deployment)

Tagged releases attach `docker-compose.release.yml` and `.env.selfhost.example`, so a server can deploy without cloning or building the repository.

Download those two files from the GitHub Release, then:

```bash
cp .env.selfhost.example .env
# edit .env:
# - pin APP_VERSION to the release tag, e.g. v1.2.3
# - set JWT_SIGNING_KEY
# - set SELFHOST_ADMIN_EMAIL / SELFHOST_ADMIN_PASSWORD for first startup
# - change POSTGRES_PASSWORD + matching DATABASE_URL password
# - configure at least one model provider

docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

The release publishes backend, frontend and MCP sandbox images to GHCR for `linux/amd64` and `linux/arm64`. See [docs/selfhost-release-images.md](./docs/selfhost-release-images.md) for image tags, reverse-proxy origins, upgrade/rollback, SBOM/provenance and vulnerability-scan details.

### Option B — build from source

For development or a custom frontend build:

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
# configure the same required secrets/provider values

docker compose up -d --build
```

The Makefile wrapper is:

```bash
make docker-up
```

Then open:

```text
http://localhost:3456
```

Useful source-tree self-host commands:

```bash
make docker-ps
make docker-logs
make selfhost-smoke
make docker-restart
make docker-down
```

`make docker-down` retains the PostgreSQL and object/artifact named volumes.

The Docker self-host baseline deliberately runs `SELF_HOSTED_MODE=1` and `LOCAL_MODE=0`. PostgreSQL persists platform/tenant data, built-in accounts, ADK Session and durable Memory; a backend-mounted Docker Volume persists user objects and ADK Artifacts. Built-in `local-jwt` authentication is the default self-host identity provider. No GCP project, Firebase project, Redis, MinIO or Keycloak is required for the baseline.

See [SELFHOST.md](./SELFHOST.md) for Linux deployment, persistence, reverse-proxy and security notes.

## Model providers

The self-host path supports OpenAI official, Gemini Developer API, Anthropic and generic OpenAI-compatible gateways. Provider routing is registry-driven rather than based on a model-name prefix.

For copyable DeepSeek, Qwen, vLLM and LiteLLM/OneAPI/NewAPI examples, see [docs/selfhost-openai-compatible.md](./docs/selfhost-openai-compatible.md).

## Source-development LOCAL_MODE baseline

For the shortest source-development loop, the platform can still run directly from source in `LOCAL_MODE=1` without Firestore, Firebase Auth, Vertex Session/Memory, GCS or Cloud Trace credentials.

### 1. Install dependencies

Install the repository prerequisites described in [WORKSHOP.md](./WORKSHOP.md), including Python/`uv`, Node.js/npm and the frontend/backend dependencies.

### 2. Configure one model provider

Copy the example environment and configure a provider supported by the current registry:

```bash
cp .env.selfhost.example backend/.env
```

For example, Gemini Developer API:

```env
GEMINI_API_KEY=your-key
```

Or an OpenAI-compatible endpoint:

```env
OPENAI_API_KEY=your-key-or-gateway-token
OPENAI_API_BASE=https://your-endpoint.example/v1
PLATFORM_DEFAULT_MODEL=<registered-model-id>
```

### 3. Start LOCAL_MODE

```bash
make dev-local
```

Expected services:

| Service | URL | Purpose |
| --- | --- | --- |
| Frontend | http://localhost:3456 | Next.js / AG-UI / A2UI renderer |
| Backend | http://localhost:1956 | FastAPI + Google ADK runtime |
| MCP Apps sandbox | http://localhost:3457 | isolated MCP App rendering |

LOCAL_MODE uses development substitutes for cloud infrastructure but keeps the real protocol/runtime path:

```text
Next.js -> FastAPI -> Google ADK -> Skill -> Tool/MCP -> AG-UI -> A2UI
```

### 4. Run the reusable smoke test

With the self-host stack running:

```bash
make selfhost-smoke
```

The underlying script verifies the backend health/API surface, frontend reachability and MCP Apps sandbox reachability, and is also exercised by the self-host CI gates.

Automated persistence/auth tests additionally cover PostgreSQL repository state, Session/Memory reconstruction, A2UI replay/state, local ObjectStorage/Artifact persistence, local JWT authentication, real Tenant A/B isolation, real MCP protocol transport and Chromium MCP Apps sandbox rendering.

The remaining final model-dependent acceptance is intentionally not replaced by mocks:

- normal Chat / Runtime Skill against a real configured Provider;
- real Provider Tool Calling;
- real model selection and execution of a bound MCP Tool;
- final Tenant quota / Tool Permission / Model Policy checks on that live model path.

Issue #1 remains the final real-protocol acceptance gate until those Provider-dependent paths have been recorded on an actual deployment.

## Cloud/development mode

The upstream cloud-oriented development flow remains available:

### Backend

```bash
cd backend
make install
make dev
```

Backend API: http://localhost:1956

### Frontend

```bash
cd frontend
npm install
npm run dev
```

For the integrated repository launcher, see the root `Makefile` and [WORKSHOP.md](./WORKSHOP.md).

## API reference

- Swagger UI: http://localhost:1956/docs
- OpenAPI JSON: http://localhost:1956/openapi.json
- Skill invocation (AG-UI streaming): `POST /api/skill/{skill_id}/stream`
- LOCAL_MODE status: `GET /api/local-mode-status`

The canonical ADK app name is currently `aitana_platform` (`APP_NAME` in `backend/adk/agui.py`). This is an upstream/internal compatibility identifier; fork branding should not infer routing from filesystem names.

## Roadmap

The self-hosting roadmap is tracked in GitHub Issues and summarized in [HANDOFF.md](./HANDOFF.md):

1. real protocol/browser acceptance gate
2. provider-driven OpenAI-compatible model routing and live Tool Calling acceptance
3. Docker Compose one-command deployment
4. PostgreSQL persistence abstraction
5. persistent Session/Memory abstraction
6. local ObjectStorage / optional S3-compatible adapter
7. built-in JWT / optional OIDC authentication
8. optionalized GCP-only capabilities
9. explicit tenant isolation and quotas
10. model provider configuration center
11. self-hosted MCP server management
12. Chinese i18n and configurable branding
13. GHCR/versioned self-host CI/CD
14. upstream synchronization strategy

The long-term goal is to add self-hosting adapters rather than delete Google Cloud support, keeping the platform usable in both deployment models.

## License

Apache License 2.0. See [LICENSE](./LICENSE).
