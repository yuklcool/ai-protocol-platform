# A2UI / AG-UI deployment and operation acceptance

The supported UI wire format is **A2UI v0.9 with the SDK basic catalog**.
AG-UI events are consumed by `@ag-ui/client`; the backend bridge remains pinned
to `ag-ui-adk==0.6.5` and `google-adk==1.31.1`. This contract does not claim
compatibility with other A2UI versions or arbitrary unregistered catalogs.

## Configure a fresh deployment

1. Follow `SELFHOST.md` to set JWT signing material, the initial admin account,
   persistent volumes and the public frontend / MCP sandbox origins.
2. Start `docker compose up -d --build` and sign in as the initial admin.
3. In Models, register the provider URL, credential reference and model; run
   both completion and tool-calling probes. The provider must support streaming
   tool calls. Keep credentials on the backend.
4. In Root Agent settings select that registered model. Bind the permitted
   Skills, native tools and MCP servers. Enable fail-closed permissions after
   binding the intended resources.
5. Enable A2UI, surface-context writes and action-triggered runs in Interaction.
   These separate controls are required for an interactive application.
6. Use `/chat/root-agent`. A new chat no longer requires choosing a Skill.
   The Agent sees an authorized catalog and loads Skill instructions through
   `load_skill`; Skills do not become separate Agents or grant extra tools.

The Skill content editor only changes instructions, supporting files and access
control. Model/tool/MCP/A2UI settings live in Root Agent settings; normal Root
chat is the place to test capabilities. See `module-simplification.md` for the
current module boundaries and retired demonstration routes.

Self-hosted chat titles use the first user turn locally. They do not invoke an
additional Gemini model unless the operator explicitly sets `CHAT_TITLE_MODEL`.
That optional title client respects `GOOGLE_GENAI_USE_VERTEXAI`; registering an
OpenAI-compatible Root model does not implicitly require Google credentials.

Both chat and UI actions use `/api/agent/stream` and the same frontend AG-UI
agent. The existing Skill stream URL is an alias of that runtime. The separate
surface-action-run route remains available for protocol clients and developer
previews, with the same current Root policy.

## Required operation sequence

The real-provider browser gate must complete all of the following on one commit:

| Operation | Evidence |
| --- | --- |
| Register a provider and model | Completion and tool-call probes succeed |
| Execute MCP from product Chat | Real model calls `show-map`; MCP App renders |
| Generate an A2UI form | Model calls the validated A2UI tool; no seeded UI |
| Enter a field and click its action | Actual browser event reaches the current Root session |
| Continue execution | AG-UI streams the run, tools, text/state and A2UI patch |
| Refresh | The form, edited value and result reconstruct from PostgreSQL |
| Operate again | The restored form remains interactive and receives another patch |
| Reject a failed or truncated run | UI shows an error, never a false success |
| Stop a running action | Shared AG-UI run is aborted and the control becomes usable |
| Isolate tenants | Same UID cannot share memory, session/app/user state or tools across tenants |

Model-authored A2UI uses the same `A2UI_SURFACE` event and persistent surface
registry as tool-authored results. A UI-only run is a valid result. Patches keep
their creation history for replay; delete/recreate lifecycle messages are applied
in order. Ordinary UI forms remain usable after reload; confirmation cards keep
their one-shot behavior.

`Protocol operation acceptance` runs the browser and Tenant A/B real-provider
workflows. Set repository variables `REAL_PROVIDER_BASE_URL` and
`REAL_PROVIDER_MODEL`, and the `REAL_PROVIDER_API_KEY` secret, for the chosen
acceptance gateway. A syntax-only PR check is not real-provider acceptance.

The deterministic `A2UI live self-host acceptance` separately checks seeded
surface persistence. It is useful regression coverage but does not substitute
for the model-generated form test.

## Existing PostgreSQL installations

Keep the existing volumes and take a database backup before upgrading. ADK
Session now partitions its storage app namespace by trusted tenant, and durable
Memory partitions by tenant/app/UID. Logical app names returned to the runtime
remain `root-agent` or the stored legacy app name.

Unattributed historical ADK rows and memory are never searched as a fallback.
They need an explicitly reviewed migration using the authoritative session index
and tenant ownership; do not infer ownership from email domains. Until the target
installation's data migration is executed and verified, existing-data upgrade
acceptance remains open. Fresh-deployment protocol acceptance and production
data migration are separate gates.

## Evidence discipline

Report unit tests, real PostgreSQL/browser tests and real-provider runs separately.
Do not close acceptance on a mocked model, seeded UI, skipped job, old commit or
an unpublished source change. The released image must identify the same commit
that passed the operation sequence.
