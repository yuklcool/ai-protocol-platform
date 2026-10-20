// Dev-only landing page for MCP Apps integration smoke routes.
// Sister to /dev/rich-media. Gated to non-prod via the layout's NODE_ENV
// check; in prod builds Next.js still ships the route but the layout
// returns notFound().
//
// See docs/archive/design/v6.1.0/mcp-app-integrations.md M3 (and the design doc
// for the sandbox proxy at docs/archive/design/v6.1.0/mcp-sandbox-separate-origin.md).

import Link from "next/link";

export const metadata = {
  title: "Aitana dev — MCP Apps smoke",
};

export default function McpAppsDevIndex() {
  return (
    <main className="page-container">
      <div className="page-body max-w-2xl space-y-6">
      <header className="page-header">
        <div className="min-w-0">
        <h1 className="page-header__title">MCP Apps — dev smoke routes</h1>
        <p className="page-header__desc">
          Fixture-driven smoke surfaces for MCPAppToolCallRouter +
          AppRenderer + the separate-origin sandbox proxy. Useful for
          iterating without standing up the full chat → backend → MCP
          server roundtrip.
        </p>
        </div>
      </header>

      <section className="glass-panel space-y-3 p-5">
        <h2 className="text-lg font-semibold">Routes</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm">
          <li>
            <Link className="inline-flex min-h-11 items-center break-all text-primary underline underline-offset-4" href="/dev/mcp-apps/passive">
              /dev/mcp-apps/passive
            </Link>{" "}
            — fixture-driven render only. Mounts AppRenderer with the
            captured ext-apps map-server tool definition + result. No
            chat-message bridge.
          </li>
          <li>
            <Link className="inline-flex min-h-11 items-center break-all text-primary underline underline-offset-4" href="/dev/mcp-apps/active">
              /dev/mcp-apps/active
            </Link>{" "}
            — full active bridge. Includes buttons that synthesise common
            iframe → host notifications and shows what the adapter
            translated them into.
          </li>
        </ul>
      </section>

      <section className="notice notice--info flex-col space-y-2 text-xs">
        <p className="font-medium">Prerequisites for the smoke routes:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <code>make dev</code> running (frontend on :3456 + sandbox on :3457)
          </li>
          <li>
            For the iframe to load actual MCP App content, point at a
            running map-server (see{" "}
            <code>docs/archive/design/v6.1.0/mcp-app-integrations.md</code> M1)
            and seed Firestore via{" "}
            <code>backend/scripts/seed_mcp_servers.py</code>
          </li>
          <li>
            For the bridge button panel only, no backend needed — the
            fixture is bundled and the adapter is pure
          </li>
        </ul>
      </section>
      </div>
    </main>
  );
}
