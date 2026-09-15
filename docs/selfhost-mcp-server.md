# Self-hosted MCP Server management

The self-host deployment can manage MCP Servers without editing Firestore or application source. The Admin control plane writes the same persisted `mcp_servers` registry consumed by the agent MCP toolset and the browser MCP proxy.

## 1. Start the optional Compose example

The repository contains a pinned wrapper around the upstream `modelcontextprotocol/ext-apps` map-server. It is opt-in so the default self-host stack stays small.

```bash
docker compose --profile mcp-example up -d --build
```

The example runs only on the Compose network. It is intentionally not published on a host port.

Use this MCP endpoint from the backend:

```text
http://mcp-example-map:8080/mcp
```

The upstream map example exposes the `show-map` tool and an MCP Apps HTML resource (`ui://cesium-map/mcp-app.html`).

## 2. Register it in Admin

Open **Administration → MCP Servers** and create a server such as:

- Server ID: `example-map`
- URL: `http://mcp-example-map:8080/mcp`
- Transport: `Streamable HTTP`
- Scope: `Tenant` for a private integration, or `Platform` for a deliberately shared integration
- Enabled: on

Tenant administrators can create or edit MCP Servers only inside their stable tenant scope. Platform-scoped servers require a platform administrator.

## 3. Credentials and secrets

Credential header values are write-only. The Admin API and Admin UI return only header names and a `has_credentials` flag.

Prefer environment references instead of putting a token directly in the registry:

```text
Authorization=${MCP_TOKEN}
X-Api-Key=${MCP_API_KEY}
```

The runtime resolves `${ENV_VAR}` immediately before building the MCP transport. An unset referenced variable fails closed instead of sending the placeholder upstream.

When editing an existing server, leave the credential field empty to keep the current stored headers. Use **Clear all stored headers on save** to remove them.

## 4. Test the server

The **Health** action performs a real MCP `initialize` handshake. It is not a TCP-only ping.

Failures are classified as:

- `network` — DNS, connection, or timeout failures
- `authentication` — authorization failures such as HTTP 401/403
- `protocol` — invalid MCP/transport behavior
- `schema` — malformed MCP result data
- `configuration` — invalid local configuration or unresolved secret references

A disabled MCP Server can still be tested by an administrator. Disabled servers are unavailable to both agent-side MCP resolution and the frontend MCP proxy.

## 5. Discover capabilities

Use **Discover** to inspect:

- `tools/list`
- `resources/list`
- `prompts/list`
- MCP Apps HTML/UI resource URIs

Resources and prompts are optional MCP capabilities; an optional capability failure is returned as a warning instead of hiding the otherwise healthy server.

## 6. Bind the MCP Server to a Skill

Select the server in the diagnostics panel, choose a visible Skill, and click **Bind**.

The page updates the existing Skill field:

```yaml
skillMetadata:
  toolConfigs:
    mcp:
      servers:
        - example-map
```

The write goes through the normal `/api/skills/{skill_id}` API. Existing Skill ownership and admin rules remain authoritative; MCP administration does not bypass them.

## 7. Runtime acceptance

After binding:

1. Keep the MCP Server enabled.
2. Open a conversation using the bound Skill.
3. Ask for an action that requires the discovered MCP tool (for the example server, the `show-map` capability).
4. Verify the agent invokes the MCP tool.
5. If the tool returns an MCP Apps resource, verify it renders through the existing MCP sandbox/proxy path.

For a negative check, disable the server in Admin and retry. Agent registry resolution and `/mcp/{server_id}` proxy access should both fail closed until it is re-enabled.

## Network note

`mcp-example-map` is a Docker service name and is resolvable from containers on the Compose network. It is **not** a URL the host browser can resolve directly. This is intentional: the browser uses the platform MCP proxy while backend/agent traffic reaches the upstream server over the private Compose network.
