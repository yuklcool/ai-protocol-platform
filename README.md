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

The current self-host baseline packages the three existing application services:

```text
frontend      :3456
backend       :1956
mcp-sandbox   :3457
```

Start from a clean host with Docker + Compose v2:

```bash
cp .env.selfhost.example .env
# edit .env and set GEMINI_API_KEY

docker compose up -d --build
```

Then open:

```text
http://localhost:3456
```

Check status and logs:

```bash
docker compose ps
docker compose logs -f
```

Stop while retaining local state:

```bash
docker compose down
```

The Compose baseline runs `LOCAL_MODE=1`, persists supported local Firestore state in a named Docker volume, builds the frontend with LOCAL_MODE enabled, and keeps MCP Apps on its separate sandbox origin.

See [SELFHOST.md](./SELFHOST.md) for Linux deployment, persistence, reverse-proxy and security notes.

## Source-development LOCAL_MODE baseline

The same core platform can be run directly from source without Firestore, Firebase Auth, Vertex Session/Memory, GCS or Cloud Trace credentials.

### 1. Install dependencies

Install the repository prerequisites described in [WORKSHOP.md](./WORKSHOP.md), including Python/`uv`, Node.js/npm and the frontend/backend dependencies.

### 2. Configure one model key

The current Phase-0 zero-GCP reference path uses Gemini Express Mode:

```bash
cp .env.selfhost.example backend/.env
```

Then edit `backend/.env` and set:

```bash
GEMINI_API_KEY=your-key
```

> Generic OpenAI-compatible endpoint support (custom Base URL + arbitrary model names such as `deepseek-chat`) is part of Roadmap Issue #2 and should not be confused with the Phase-0 baseline.

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

LOCAL_MODE uses in-memory/local substitutes for cloud infrastructure but keeps the real protocol/runtime path:

```text
Next.js -> FastAPI -> Google ADK -> Skill -> Tool/MCP -> AG-UI -> A2UI
```

### 4. Run the reusable smoke test

With the stack running:

```bash
bash scripts/smoke-selfhost.sh
```

The automated smoke test verifies:

- backend `/health`
- `LOCAL_MODE=1` runtime status
- FastAPI/OpenAPI route registration
- Skill streaming API registration
- MCP-related API surface
- frontend reachability
- MCP Apps sandbox reachability

It then prints the manual acceptance checklist for the real model-dependent flows:

- normal Chat
- Runtime Skill
- `Workspace Demo` A2UI surface
- A2UI action round-trip
- MCP Tool call
- MCP App iframe/sandbox rendering

Issue #1 should only be closed after those model-dependent checks have also been completed successfully on a real development machine.

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

1. LOCAL_MODE reproducible baseline and smoke tests
2. provider-driven OpenAI-compatible model routing
3. Docker Compose one-command deployment
4. PostgreSQL persistence abstraction
5. persistent Session/Memory abstraction
6. S3/MinIO object storage
7. JWT/OIDC/Keycloak authentication
8. optionalize remaining GCP-only capabilities
9. explicit tenant isolation and quotas
10. model provider configuration center
11. self-hosted MCP server management
12. Chinese i18n and configurable branding
13. GHCR/versioned self-host CI/CD
14. upstream synchronization strategy

The long-term goal is to add self-hosting adapters rather than delete Google Cloud support, keeping the platform usable in both deployment models.

## License

Apache License 2.0. See [LICENSE](./LICENSE).
