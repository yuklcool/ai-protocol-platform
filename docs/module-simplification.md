# Platform module boundaries

The product has one Root Agent, one chat/workbench and one protocol runtime.
Configure model, tools, MCP, knowledge bindings and interaction in `/agent`.
Manage reusable capability content in `/skills`.

## Skill content editor

Skill Studio edits only name, description, instructions, references, assets and
access control. It does not start a second chat or authoring Agent. Test saved
capabilities in the normal Root Agent chat, with the actual Root bindings and
tenant policy.

Saving an existing Skill submits only the edited content fields. Legacy model,
tool, delegation, persona, welcome, shell and protocol fields stay in storage for
API compatibility; a content edit does not reset them. They are not independent
Agent settings. Runtime permission ceilings continue to come from Root and the
authenticated tenant/user policy.

Reference and asset contents are returned by authorized individual Skill reads,
creation and updates. The list/catalog responses omit those files. Duplicate or
empty file names are rejected by the editor before saving.

## Removed modules

- The old Skill switcher and Skills bar, unused split-pane shell, unused budget
  banner, read-only composer and unreferenced helper modules.
- Skill-owned model/tool/MCP/A2UI/delegation/persona editors, duplicate test-chat
  renderer and authoring Copilot/proposal runtime.
- Hard-coded file-browser fixtures, rich-media showcase and the runtime Markdown
  workshop renderer. The old Knowledge menu pointed to fixture data; knowledge
  bindings are configured in Root settings. Document upload/view remains in the
  real chat/workbench.
- Unused frontend Cloud Firestore/Storage server SDKs, Radix packages and class
  variant dependency, plus the seed command whose script did not exist.

Old `/agents`, `/agents/:id`, `/skills/new`, fixture and workshop URLs are handled
by one Next.js redirects table. There are no separate redirect page components.
Local-mode guidance links to `SELFHOST.md`, which covers durable private hosting
without requiring GCP.

## Retained modules

A2UI, AG-UI, MCP/MCP Apps, document handling, sessions/memory, authentication,
tenant isolation, model policy, quota, audit and self-host release checks remain.
The A2UI and MCP diagnostic routes remain available for protocol development and
acceptance, outside the product navigation. Active protocol/error/cancellation
tests remain part of the test suite; tests for removed UI modules are removed
with their implementations.

Optional messaging channels import their adapters only when their existing
credential environment variables enable them. An ordinary web deployment does
not initialize Discord, Telegram, Mailgun or Twilio adapters.

No data migration or production upgrade is performed by this refactor. Existing
ADK Session/Memory namespace migration acceptance remains tracked in issue #9.
