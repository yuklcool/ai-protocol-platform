# Real Provider → Agent → MCP acceptance

A separate no-external-model CI gate (`model-provider-studio-live`) continuously proves that a database-backed dynamic model appears in the real Skill Studio UI, can be selected, saved, and survives reload. It deliberately does not call the configured model endpoint.

This is the remaining real-model boundary for issues #2, #10 and #11. It uses
an actual external OpenAI-compatible model and a real MCP server through the
normal browser chat flow. Before chat, the same browser session opens Skill Studio, verifies the dynamic database-backed model is present in the model selector, selects it, saves the Skill, and re-reads the persisted Skill metadata. It does not use a fixed model response or ToolCall.

## Configure and run

1. Add repository Actions secret `REAL_PROVIDER_API_KEY` containing the provider
   credential. Do not put the credential in workflow inputs, issues, or commits.
2. Open GitHub Actions → **Real Provider Agent MCP acceptance** → **Run workflow**.
3. Select `main`, then supply:
   - `provider_base_url`: externally reachable OpenAI-compatible API base URL,
     including its API prefix (for example `https://api.example.com/v1`).
   - `model_api_name`: the upstream model name, with tool calling support.
   - `supports_reasoning`: enable only when the model requires the probe to use
     `max_completion_tokens` instead of `max_tokens`.
4. Inspect the **real-provider-agent-mcp** job, not just the syntax job.

The endpoint must support `/models` and `/chat/completions` and be reachable
from GitHub-hosted runners. A private endpoint needs a runner with appropriate
network access. The workflow makes real billable model requests.

## What runs

The workflow starts an isolated Compose stack with PostgreSQL, local JWT,
backend, frontend, a separate-origin MCP Apps sandbox and the ext-apps map
server. It registers an environment-secret reference, probes completion/tool
calling, creates a private Skill using the dynamic model, and sends a user turn
through Chromium `/chat/{skillId}`. The real model must select `show-map`, the
call must succeed, an MCP App iframe must mount, and the assistant must produce
the final marker after the tool result.

Provider, model, Skill and MCP registry names have a per-run random suffix;
cleanup does not overwrite or remove the normal `ext-apps-map` registration.
The GitHub job removes its disposable Compose volumes when it ends.

## Evidence and limits

A pull-request syntax check passing is **not** real Provider acceptance. The
full job is manual-only and fails when the secret or required inputs are absent.
Record the run URL, tested commit, provider/model and result in HANDOFF and the
relevant issues after an actual run. Never record the credential.

This workflow creates the Skill via the API, so it does not prove the Skill
Studio model-selection UI. It also does not test Tenant A/B quota accounting,
permission bypass, or migration against existing deployment data. Keep those
acceptance items open until separately verified. An iframe mounting alone does
not add new rendering evidence beyond the existing MCP Apps browser gate.

## Tenant A/B live acceptance

The provider-independent `scripts/smoke-tenant-isolation.sh` covers identity,
tenant-scoped Session, document storage, model policy, MCP configuration and
audit boundaries. It intentionally does not claim a model spend or Tool Call.

For the remaining live-provider boundary, run the tenant acceptance with
`BUDGET_ENFORCER=tenant-repository`, two real provider model registrations and
two tenant-scoped MCP bindings. The fixture seeder accepts
`TENANT_E2E_MODEL_A`, `TENANT_E2E_MODEL_B`, `TENANT_E2E_QUOTA_USD_A` and
`TENANT_E2E_QUOTA_USD_B`, so the run can select the exact provider-backed model
ids and non-zero quota policies instead of accidentally using the first YAML
model. The acceptance must prove both tenants can complete their own Root Agent
Tool Calling path, cross-tenant capability hints return 404, and a subsequent
turn receives the typed `BUDGET_EXCEEDED` event. Do not close #9 from a syntax
check or a provider-only run; attach the live run URL and tenant evidence.

### Executable tenant runner

Use the manual **Tenant A/B real Provider acceptance** workflow for this
boundary. It accepts the same OpenAI-compatible base URL and model inputs as
the existing Provider/MCP workflow, and reads the provider credential only from
the REAL_PROVIDER_API_KEY Actions secret.

The workflow starts an isolated PostgreSQL Compose stack with
BUDGET_ENFORCER=tenant-repository and runs
scripts/smoke-tenant-provider-acceptance.mjs. The selected upstream model must
support Tool Calling and match a configured platform pricing entry. The runner
rejects a zero-price model or a Provider response without recorded token usage:
a projected hold alone is not sufficient evidence of real quota consumption.

It registers two distinct model ids for the real Provider, seeds two tenants
whose local-JWT users intentionally share a uid, creates one tenant-scoped MCP
binding and private Skill per tenant, and sends every turn through the Root
Agent stream. A passing live run proves all of the following:

- Tenant A and Tenant B both complete their own real show-map MCP Tool Call.
- Each tenant has a positive, recorded budget-ledger charge.
- Tenant B receives 404 when it requests Tenant A's private capability.
- After Tenant A's cap is reduced below recorded spend, its next turn emits
  typed BUDGET_EXCEEDED before any Tool Call.
- Tenant B can still make another successful Tool Call after Tenant A exhausts
  its own quota.

The pull-request job only validates runner syntax and never receives the
credential. Attach the successful manual-run URL, commit, provider/model and
redacted tenant evidence before closing the live-provider part of #9. The
separate target-deployment legacy-migration dry-run, review, apply and verify
remains required.
