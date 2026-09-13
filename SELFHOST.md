# Self-hosting guide

This document describes the current Phase-0/Phase-1 self-hosted baseline for `ai-protocol-platform`.

The goal is deliberately narrow: run the existing protocol stack with Docker Compose before replacing every Google Cloud dependency with PostgreSQL, MinIO and OIDC. Those adapters remain separate roadmap items.

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
  └── MCP Apps integration

mcp-sandbox :3457
  └── separate-origin iframe host
```

The backend runs with `LOCAL_MODE=1`:

- Firestore is replaced by the local/in-memory implementation.
- Firebase authentication is replaced by the LOCAL_MODE stub identity.
- ADK sessions use in-memory mode.
- Cloud Trace / Cloud Logging exporters are disabled.
- GCS artifacts and Vertex Search are not required for startup.
- local Firestore state is mounted at `/root/.aitana-local` and persisted in a named Docker volume.

This is a self-hosted development/single-node baseline, not yet the final multi-node production architecture.

## Requirements

A Linux server needs:

- Docker Engine
- Docker Compose v2 (`docker compose`)
- outbound HTTPS access to the configured model provider
- ports 3456, 1956 and 3457 available, or equivalent reverse-proxy mappings

No GCP project or Firebase credentials are required for the baseline.

## Quick start

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
```

Configure at least one model provider in `.env`. For the shortest zero-GCP path:

```env
GEMINI_API_KEY=your-key
```

For OpenAI:

```env
OPENAI_API_KEY=your-key
OPENAI_API_BASE=https://api.openai.com/v1
```

For an OpenAI-compatible service such as DeepSeek, Qwen gateway, vLLM, LiteLLM Proxy, OneAPI/NewAPI, or an internal gateway:

```env
OPENAI_API_KEY=your-key-or-local-placeholder
OPENAI_API_BASE=http://model-gateway.example:8000/v1
```

Then build and start:

```bash
docker compose up -d --build
```

Check service state:

```bash
docker compose ps
```

Expected browser endpoint:

```text
http://SERVER_IP:3456
```

Backend API:

```text
http://SERVER_IP:1956/docs
```

MCP Apps sandbox:

```text
http://SERVER_IP:3457/sandbox.html
```

## OpenAI-compatible model registry

Provider routing is registry-driven. The backend no longer requires an OpenAI-compatible model name to begin with `gpt-`.

Add the model to `backend/config/models.yaml` using the exact model name exposed by the endpoint. Example:

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
    context_window: 128000       # replace with the real provider/model limit
    max_output_tokens: 8192      # replace with the real provider/model limit
    description: "DeepSeek through an OpenAI-compatible endpoint"
```

Then configure a Skill to use the registry ID:

```yaml
model: deepseek-v3
```

The same mechanism works for Qwen, vLLM-served models and proxy aliases. `api_name` is opaque to the platform; `provider: openai` selects LiteLLM's OpenAI-compatible transport.

Capabilities are explicit:

- `supports_tools`: the endpoint/model is expected to support tool/function calling.
- `supports_reasoning`: send a reasoning effort parameter.
- `supports_responses_api`: enable the Responses-API reasoning bridge used by compatible OpenAI reasoners.

For a Chat-Completions-only compatible endpoint, leave `supports_responses_api: false`. A model can declare `supports_reasoning: true` with `supports_responses_api: false`; in that case the backend sends reasoning effort without enabling the Responses bridge.

Legacy raw official names such as `gpt-*`, `o1*`, `o3*`, `o4*`, `gemini-*` and `claude-*` remain supported for backward compatibility. Non-standard raw names should be registered explicitly so provider and capability behavior is deterministic.

## Smoke test

From the repository directory:

```bash
BACKEND_URL=http://127.0.0.1:1956 \
FRONTEND_URL=http://127.0.0.1:3456 \
SANDBOX_URL=http://127.0.0.1:3457 \
bash scripts/smoke-selfhost.sh
```

The script verifies process/API reachability and prints the remaining real-model protocol acceptance checklist.

Before treating a build as a valid baseline, manually verify:

1. a normal Chat turn;
2. a Runtime Skill turn;
3. `Workspace Demo` renders an A2UI surface;
4. an A2UI action reaches the Agent and produces a follow-up result;
5. at least one MCP Tool executes;
6. at least one MCP App renders inside the separate sandbox origin.

For an OpenAI-compatible deployment, also verify one tool-calling turn using the configured non-`gpt-*` model name. This is the live acceptance step that unit tests cannot replace.

## Persistence

Compose enables:

```env
LOCAL_MODE_PERSIST=1
```

and mounts:

```text
ai-protocol-platform-local-state -> /root/.aitana-local
```

This preserves the local Firestore fixture/state supported by the current LOCAL_MODE implementation. Session and artifact persistence are still separate roadmap items; do not treat this volume as the final PostgreSQL/MinIO persistence layer.

To remove the stack while keeping the volume:

```bash
docker compose down
```

To remove the stack and the local state volume:

```bash
docker compose down -v
```

## Reverse proxy / TLS

For an internet-facing server, place Caddy, Nginx, Traefik or another TLS reverse proxy in front of the frontend. The browser-facing frontend and MCP sandbox must remain different origins because MCP Apps are intentionally isolated from the host application.

For example, use separate hostnames:

```text
https://ai.example.com      -> frontend:8080
https://mcp.example.com     -> mcp-sandbox:8080
```

When changing origins, also update the frontend build arguments and sandbox `ALLOWED_HOST_ORIGINS`. Do not collapse the MCP App sandbox onto the same origin merely to simplify proxying.

## Security boundary of this baseline

`LOCAL_MODE` intentionally uses a stub identity. It is suitable for local development and controlled single-user/self-host testing. The backend contains a safety guard that refuses LOCAL_MODE when common Cloud Run/App Engine/Kubernetes deployment markers are present, but that guard is not a substitute for real production authentication.

Before exposing the platform to untrusted users, complete the roadmap work for:

- JWT/OIDC/Keycloak authentication;
- explicit tenant isolation;
- persistent database-backed authorization data;
- secret management;
- rate limits and quotas;
- audit retention.

## Next infrastructure phases

The Compose file is intentionally kept to the three existing application services first. Planned additions are staged behind their adapters:

```text
Phase 0/1   frontend + backend + mcp-sandbox
Phase 2     + PostgreSQL
Phase 2     + MinIO/S3
Phase 2     + OIDC/Keycloak (optional profile)
```

This preserves the upstream architecture and gives each infrastructure replacement an independently testable migration path.
