# Upstream synchronization strategy

This repository is a long-lived self-hosted fork of:

- Upstream: `sunholo-data/ai-protocol-platform`
- Upstream default branch: `main`
- Fork: `yuklcool/ai-protocol-platform`
- Fork integration branch: `main`

The goal is to keep receiving upstream ADK, AG-UI, A2UI, MCP/MCP Apps and frontend improvements without re-implementing the fork's Self-host, persistence, identity, tenant, model-provider and release work after every upstream update.

## Core rule

**Never merge upstream directly into `main`.**

Every upstream update goes through a temporary `sync/upstream-YYYYMMDD[-N]` branch and a normal pull request. The sync PR must pass the same server-authoritative Self-host/Tenant/MCP/Provider regressions as any other architecture-changing PR before it can be merged.

The frozen deployment branch `deploy/2026-09-15` must never be moved by upstream synchronization.

## Repository boundaries

### Keep as upstream-compatible as practical

These areas carry protocol/runtime behavior we want to continue receiving from upstream. Prefer small, reviewable changes and extension seams instead of fork-only rewrites:

- `backend/adk/` — Google ADK agent/runtime integration
- frontend AG-UI/A2UI rendering and chat protocol components
- MCP/MCP Apps host/client protocol handling
- `infrastructure/mcp-sandbox/`
- generic skill/runtime contracts
- protocol-focused tests and examples

When upstream changes one of these areas, preserve upstream protocol behavior first, then re-apply fork-specific policy through existing adapters/configuration seams.

### Fork-owned extension seams

Self-host-specific behavior should live here (or in equivalent provider/adapter modules) rather than being scattered through protocol code:

- persistence/repository adapters (PostgreSQL plus optional cloud adapters)
- identity providers (`local-jwt`, optional Firebase/OIDC adapters)
- object/artifact storage adapters
- model Provider Registry/runtime model resolver
- MCP Server Registry/Admin configuration
- first-class Tenant/policy/audit/budget enforcement
- Self-host Compose/release/migration scripts
- admin/configuration UI surfaces

New Self-host work should prefer these seams before editing upstream-sensitive protocol code.

### Expected conflict zones

The following files/directories are intentionally customized and require explicit review during every upstream sync:

- `docker-compose*.yml`
- `.env.selfhost.example`
- `SELFHOST.md`, `HANDOFF.md`, `UPSTREAM.md`
- `backend/config/` and runtime provider/persistence/auth wiring
- admin routes and admin frontend pages
- tenant authorization/policy enforcement
- release and self-host GitHub Actions
- branding/i18n configuration

Do not resolve these conflicts with a blanket `ours` or `theirs` strategy.

## Invariants that an upstream sync must not break

1. Production Self-host remains `SELF_HOSTED_MODE=1`, `LOCAL_MODE=0`.
2. PostgreSQL remains the default durable structured-state backend.
3. Local persistent volume remains the default object/artifact storage path.
4. `local-jwt` remains the default Self-host identity provider; Firebase/GCP remain optional adapters.
5. Tenant/Auth/Permission decisions remain server-authoritative and fail closed.
6. Browser-provided tenant/role/group claims are never treated as authorization truth.
7. Dynamic models continue through the unified model registry/runtime resolver.
8. MCP credentials and Provider API-key references are never returned as plaintext.
9. MCP Apps keep a separate sandbox origin.
10. AG-UI/A2UI/MCP protocol paths are not replaced with fork-only proprietary equivalents.
11. GCP support is not deleted merely to simplify Self-host; it remains an optional adapter/provider.
12. Brand/product copy belongs in the branding/i18n configuration layer where possible; avoid scattering fork names through protocol/business code.
13. `deploy/2026-09-15` remains immutable.

## Sync procedure

### 1. Inspect upstream drift

The scheduled/manual `Upstream compare` GitHub Action fetches upstream `main`, records the upstream SHA, merge base, ahead/behind counts, changed paths and a merge-tree conflict preview. It is reporting-only and never pushes or merges code.

Local equivalent:

```bash
git remote add upstream https://github.com/sunholo-data/ai-protocol-platform.git 2>/dev/null || true
git fetch upstream main
git rev-list --left-right --count main...upstream/main
git diff --name-status main...upstream/main
git merge-tree --write-tree main upstream/main
```

### 2. Create a sync branch

```bash
git switch main
git pull --ff-only origin main
git switch -c sync/upstream-YYYYMMDD
git fetch upstream main
git merge --no-ff upstream/main
```

Resolve conflicts explicitly. Do not modify the frozen deploy branch.

### 3. Review by subsystem

Classify incoming changes before resolving them:

- protocol/runtime: ADK, AG-UI, A2UI, MCP/MCP Apps
- frontend/UI
- persistence/storage
- auth/tenant/security
- model/provider
- deployment/release
- docs/examples

For fork-owned changes, keep policy in adapters/providers/config layers. If a conflict requires a new direct divergence in upstream-sensitive code, add it to the divergence log below in the same PR.

### 4. Open a normal PR to `main`

The PR description should record:

- upstream SHA being synchronized
- previous fork/main SHA
- major upstream changes adopted
- conflicts and how each was resolved
- new/removed divergences
- regression results

### 5. Required regression gates

A sync PR is not mergeable by process until the applicable existing gates are green, including at minimum:

- Self-host baseline
- Self-host auth baseline
- Self-host no-GCP gate
- Core runtime persistence
- Tenant isolation / Tenant live self-host acceptance
- MCP admin gate
- MCP live self-host acceptance (including browser sandbox coverage where triggered)
- Model provider gate
- frontend typecheck/tests for changed frontend code

If release files are touched, `Self-host release images` must also pass. If a real-Provider boundary is changed, run the manual real Provider acceptance before calling that boundary verified.

CI that uses fixtures does not substitute for an explicitly required real external Provider or target-deployment migration acceptance.

### 6. Merge and record

After the sync PR is merged:

- update the divergence log when architecture boundaries changed;
- update `HANDOFF.md` if operational behavior or the recommended next step changed;
- preserve the upstream SHA in the PR/merge history;
- create a new deployment snapshot branch only when a new stable deployment is intentionally cut. Never repoint an old deployment snapshot.

## Divergence log

This is an architecture-level log, not a list of every changed file. Update it when a sync adds, removes or materially changes one of these decisions.

| Area | Fork decision | Why it diverges | Upstream-sync rule |
| --- | --- | --- | --- |
| Persistence | Repository abstraction + PostgreSQL Self-host backend | Durable Self-host without Firestore/GCP dependency | Keep upstream cloud adapter support; reconcile new domain fields through repository contracts |
| Session/Memory | PostgreSQL-backed ADK Session and durable Memory | Minimize default infrastructure | Preserve ADK semantics while mapping new upstream event/state fields into the PostgreSQL adapter |
| Object/Artifact storage | Local volume default, cloud adapters optional | Minimal Self-host stack | Do not hard-code local paths into upstream protocol code |
| Identity | Built-in PostgreSQL/local-JWT default, external IdPs optional | Self-host must start without Firebase | Upstream auth changes enter through the IdentityProvider boundary; authorization stays server-side |
| Tenant boundary | Explicit stable `tenant_id`, fail-closed resource/policy isolation | Domain-only ownership is insufficient | Never weaken stable tenant scoping to accept browser/domain guesses |
| Model routing | Dynamic Provider/Model Registry with per-provider Base URL + secret ref | Multiple OpenAI-compatible/self-host gateways | Reconcile upstream model features through the unified resolver rather than model-name heuristics |
| MCP management | Persisted MCP Registry/Admin + tenant scope + skill binding/proxy | Self-host configuration without source edits | Preserve MCP protocol compatibility; credentials remain write-only/redacted |
| Self-host deployment | PostgreSQL + backend + frontend + separate MCP sandbox, minimal dependencies | Production-style no-GCP default | Do not add Redis/MinIO/Keycloak/etc. as mandatory dependencies without an explicit architecture decision |
| Release | Versioned prebuilt Self-host images/release Compose | No-clone deployment path | Release changes must pass Self-host release gates and preserve separate sandbox origin |
| Branding/i18n | Configuration layer preferred over source-wide product-name edits | Reduce future upstream conflicts | New product copy should be configurable; legal attribution/licensing remains intact |

## What must not be automated

The compare workflow may report drift and conflicts, but it must not automatically merge upstream into `main`, rewrite conflict resolutions, move deployment snapshots, or mark real-environment acceptance complete. Those steps require a reviewed sync PR and evidence from the relevant gates.
