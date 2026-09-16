# Self-host deployment with versioned GHCR images

This is the recommended deployment path when you want to run AI Protocol Platform without cloning or building the source tree.

A tagged release publishes three multi-architecture images:

```text
ghcr.io/yuklcool/ai-protocol-platform-backend:<version>
ghcr.io/yuklcool/ai-protocol-platform-frontend:<version>
ghcr.io/yuklcool/ai-protocol-platform-mcp-sandbox:<version>
```

Supported release architectures:

```text
linux/amd64
linux/arm64
```

The GitHub Release also attaches:

```text
docker-compose.release.yml
.env.selfhost.example
```

The release Compose file has no source build contexts and no source-code bind mounts. PostgreSQL schema migrations are bundled in the backend image and applied idempotently before the backend starts.

## 1. Download the release assets

From a GitHub Release, download:

```text
docker-compose.release.yml
.env.selfhost.example
```

Then:

```bash
cp .env.selfhost.example .env
```

No repository checkout is required.

## 2. Pin the release version

For production, pin the exact semver release:

```env
APP_VERSION=v1.2.3
```

`latest` is convenient for evaluation, but should not be used as the production rollback boundary.

Every published image also receives an exact source tag:

```text
sha-<full-git-commit-sha>
```

You can deploy that tag by setting `APP_VERSION` to the matching `sha-*` value, or override `BACKEND_IMAGE`, `FRONTEND_IMAGE`, and `MCP_SANDBOX_IMAGE` independently.

## 3. Configure authentication and persistence

At minimum configure:

```env
JWT_SIGNING_KEY=<random-secret-at-least-32-bytes>
SELFHOST_ADMIN_EMAIL=admin@example.com
SELFHOST_ADMIN_PASSWORD=<strong-password>
POSTGRES_PASSWORD=<strong-database-password>
DATABASE_URL=postgresql://aip:<same-password>@postgres:5432/aip
```

Generate a signing key with:

```bash
openssl rand -base64 48
```

The default deployment uses:

```text
PostgreSQL
built-in local JWT
local Docker volume for objects/artifacts
MCP Apps separate-origin sandbox
```

Redis, MinIO, Keycloak, Firebase and a GCP project are not required for the baseline.

## 4. Configure a model provider

Configure at least one provider before normal Agent conversations are expected to work.

OpenAI-compatible example:

```env
PLATFORM_DEFAULT_MODEL=<registered-model-id>
OPENAI_API_KEY=<provider-key>
OPENAI_API_BASE=https://your-provider.example/v1
```

The platform can also use dynamically registered providers/models through the Model Provider administration UI. See `docs/selfhost-openai-compatible.md` for DeepSeek, Qwen, vLLM, LiteLLM/OneAPI/NewAPI patterns.

## 5. Browser-visible origins

MCP Apps require the sandbox to live on a different browser origin from the frontend.

For a local deployment the defaults are sufficient:

```env
MCP_SANDBOX_PUBLIC_URL=http://localhost:3457
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=http://localhost:3456
ALLOW_ORIGINS=http://localhost:3456
```

For an internet-facing deployment, use two HTTPS origins, for example:

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
```

Then route:

```text
https://ai.example.com  -> frontend:8080
https://mcp.example.com -> mcp-sandbox:8080
```

The versioned frontend image contains a sandbox-URL placeholder rather than a hard-coded public host. On container start it replaces that placeholder with `MCP_SANDBOX_PUBLIC_URL`, so the same published image can be deployed behind different domains without rebuilding Next.js.

Use TLS for any internet-facing deployment. The built-in browser authentication uses bearer tokens and must not traverse an unencrypted public connection.

## 6. Pull and start

```bash
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Check status:

```bash
docker compose -f docker-compose.release.yml ps
```

Default local endpoints:

```text
Frontend:         http://localhost:3456
Backend API:      http://localhost:1956/docs
MCP Apps sandbox: http://localhost:3457/sandbox.html
```

## 7. Database migrations

The backend image runs:

```text
scripts/apply_selfhost_migrations.py
```

before account/bootstrap seeding and before Uvicorn starts.

Applied migration filenames are recorded in:

```text
platform_schema_migrations
```

The runner is idempotent and is safe on existing installations that originally received `001_postgres_documents.sql` through PostgreSQL `docker-entrypoint-initdb.d`.

Do not remove or rename an already released migration file. Add a new ordered SQL migration instead.

## 8. Upgrade and rollback

Upgrade:

```bash
# edit APP_VERSION in .env to the target release
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Application-image rollback:

```bash
# restore the prior APP_VERSION
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

A database migration may be forward-only. Before upgrading production, back up both:

```text
1. PostgreSQL
2. object-data volume (/data/objects + /data/artifacts)
```

Changing an image tag is not a substitute for restoring a database backup when an incompatible schema migration has already been applied.

## 9. Supply-chain checks

The release workflow:

- builds backend, frontend and MCP sandbox images;
- builds `linux/amd64` and `linux/arm64` manifests for release tags;
- publishes semver, `latest`, and `sha-*` tags;
- generates BuildKit SBOM and provenance attestations;
- scans each published image with Trivy for HIGH/CRITICAL vulnerabilities with fixes available;
- creates GitHub Release notes and attaches the release Compose/env files.

Pull-request builds do not publish packages. They build the release images for `linux/amd64` and run the self-host release gate first.

## 10. Source build versus image pull

Use the versioned image path for normal operations:

```bash
docker compose -f docker-compose.release.yml up -d
```

Use the source-build path when developing or intentionally producing a custom frontend bundle:

```bash
git clone https://github.com/yuklcool/ai-protocol-platform.git
cd ai-protocol-platform
cp .env.selfhost.example .env
docker compose up -d --build
```

The source Compose remains the development/rebuild path. `docker-compose.release.yml` is the deployment artifact intended to satisfy the no-clone, reproducible self-host release path.
