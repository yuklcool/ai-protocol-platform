// /dev/mcp-apps/passive — fixture-driven render of MCPAppToolCallRouter.
// No chat-message bridge; just confirms the router mounts AppRenderer for
// a real captured CallToolResult and surfaces any AppRenderer.onError.
//
// Run: open http://localhost:3456/dev/mcp-apps/passive (requires `make dev`
// so the sandbox proxy on :3457 is up and map-server is on :3001).
// No Firebase login needed — uses a direct unauthenticated client to
// localhost:3001/mcp (dev-only path).

"use client";

import { useEffect, useState } from "react";
import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { createDevDirectMcpClient } from "@/lib/mcpClient";
import { TRANSPORT_FIELD } from "@/lib/branding";
import { MCPAppToolCallRouter } from "@/components/protocols/MCPAppToolCallRouter";
import type { ToolCallState } from "@/hooks/useSkillAgent";
import showMapResult from "@/components/protocols/__tests__/fixtures/map-server-show-map-result.json";

// Single fixture-driven tool call — name is the bare tool, the router will
// match it against the configured server id (MCPAppToolCallRouter currently
// expects "<server_id>_<tool>" but also supports the bare-name fallback
// when only one MCP server is configured for the skill).
const FIXTURE_TOOL_CALL: ToolCallState = {
  id: "fixture-show-map-1",
  name: "show-map",
  status: "success",
  parentMessageId: "fixture-asst-1",
  argsJson: JSON.stringify({
    west: 11.4,
    south: 48.0,
    east: 11.7,
    north: 48.2,
    label: "Munich",
  }),
  resultContent: JSON.stringify(showMapResult.result),
};

export default function McpAppsPassivePage() {
  const [devClient, setDevClient] = useState<Client | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setDevClient(null);
    const client = createDevDirectMcpClient("http://localhost:3001/mcp");
    const transport = (client as unknown as Record<string, unknown>)[TRANSPORT_FIELD] as Parameters<
      Client["connect"]
    >[0];
    client.connect(transport).then(
      () => { if (!cancelled) setDevClient(client); },
      () => { if (!cancelled) setError("Could not connect to localhost:3001/mcp. Start the map-server and retry."); },
    );
    return () => {
      cancelled = true;
      void client.close().catch(() => console.warn("passive: map-server client cleanup failed"));
    };
  }, [revision]);

  return (
    <main className="page-container">
      <div className="page-body max-w-3xl space-y-6">
      <header className="page-header">
        <div className="min-w-0">
        <h1 className="page-header__title">MCP Apps passive smoke</h1>
        <p className="page-header__desc">
          Fixture: <code>map-server-show-map-result.json</code>. Mounts
          MCPAppToolCallRouter with no <code>onChatMessage</code> bridge.
          Connects directly to <code>localhost:3001/mcp</code> (no Firebase
          auth needed). The iframe should render the Cesium globe; if it
          does not, check that <code>make dev</code> is running and both the
          sandbox proxy (:3457) and map-server (:3001) are up.
        </p>
        {!devClient && !error && (
          <p className="notice notice--warning mt-3" role="status">Connecting to map-server…</p>
        )}
        {error && <div className="notice notice--danger mt-3 flex-wrap" role="alert"><p>{error}</p><button type="button" className="button-secondary" onClick={() => setRevision(value => value + 1)}>Retry connection</button></div>}
        </div>
      </header>

      {devClient && <section className="glass-panel p-5">
        <MCPAppToolCallRouter
          toolCalls={[FIXTURE_TOOL_CALL]}
          mcpServerIds={["ext-apps-map"]}
          devClient={devClient}
        />
      </section>}
      </div>
    </main>
  );
}
