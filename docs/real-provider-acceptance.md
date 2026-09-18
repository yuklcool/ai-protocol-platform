# Real Provider → Agent → MCP acceptance

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
