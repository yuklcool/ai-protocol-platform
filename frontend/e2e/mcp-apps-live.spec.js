const { test, expect } = require("@playwright/test");

const FRONTEND_URL = process.env.MCP_BROWSER_FRONTEND_URL || "http://localhost:3456";
const BACKEND_URL = process.env.MCP_BROWSER_BACKEND_URL || "http://127.0.0.1:1956";
const ADMIN_EMAIL = process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com";
const ADMIN_PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD || "";
const RUN_ID = (process.env.MCP_E2E_RUN_ID || `${Date.now()}`)
  .toLowerCase()
  .replace(/[^a-z0-9-]/g, "-")
  .slice(0, 24);
const SERVER_ID = "ext-apps-map";
const UPSTREAM_URL = "http://mcp-example-map:8080/mcp";
const SESSION_KEY = "aitana:local_jwt_session";

async function api(path, init = {}) {
  const response = await fetch(`${BACKEND_URL}${path}`, init);
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    throw new Error(`${init.method || "GET"} ${path} -> ${response.status}: ${text}`);
  }
  return body;
}

async function authedApi(token, path, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  return api(path, { ...init, headers });
}

test.describe("real MCP Apps browser acceptance", () => {
  test.setTimeout(90_000);

  test("renders a real ui:// resource through the separate-origin sandbox", async ({ browser }) => {
    expect(ADMIN_PASSWORD, "SELFHOST_ADMIN_PASSWORD must be configured").not.toBe("");

    const login = await api("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    const token = login.access_token;
    expect(token).toBeTruthy();
    expect(login.user?.groupTags || []).toContain("aitana-admin");

    const skillName = `mcp-browser-${RUN_ID}`;
    let skillId = null;
    let serverCreated = false;
    let context = null;

    try {
      const skill = await authedApi(token, "/api/skills", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: skillName,
          description: "Browser MCP Apps acceptance skill",
          instructions: "Use the bound map MCP server.",
          displayName: "MCP Browser Acceptance",
          accessControl: { type: "private" },
          skillMetadata: {},
        }),
      });
      skillId = skill.skillId;
      expect(skillId).toBeTruthy();

      await authedApi(token, `/api/admin/mcp-servers/${SERVER_ID}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          url: UPSTREAM_URL,
          transport: "streamable-http",
          scope: "platform",
          enabled: true,
          description: "real browser MCP Apps acceptance",
        }),
      });
      serverCreated = true;

      const health = await authedApi(token, `/api/admin/mcp-servers/${SERVER_ID}/health`, {
        method: "POST",
      });
      expect(health.ok).toBe(true);

      const discovery = await authedApi(token, `/api/admin/mcp-servers/${SERVER_ID}/discover`, {
        method: "POST",
      });
      expect(discovery.ok).toBe(true);
      expect(discovery.mcp_apps?.supported).toBe(true);
      expect(discovery.mcp_apps?.resourceUris?.some((uri) => String(uri).startsWith("ui://"))).toBe(true);
      expect(discovery.tools?.some((tool) => tool.name === "show-map")).toBe(true);

      await authedApi(token, `/api/skills/${skillId}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          skillMetadata: { toolConfigs: { mcp: { servers: [SERVER_ID] } } },
        }),
      });

      context = await browser.newContext();
      const localJwtSession = {
        token,
        expiresAt: Date.now() + Number(login.expires_in || 3600) * 1000,
        user: login.user,
      };
      await context.addInitScript(
        ({ key, session }) => window.sessionStorage.setItem(key, JSON.stringify(session)),
        { key: SESSION_KEY, session: localJwtSession },
      );

      const page = await context.newPage();
      const diagnostics = [];
      page.on("console", (msg) => diagnostics.push(`[console:${msg.type()}] ${msg.text()}`));
      page.on("pageerror", (err) => diagnostics.push(`[pageerror] ${err.message}`));

      await page.goto(`${FRONTEND_URL}/dev/mcp-apps/active`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "MCP Apps active smoke" })).toBeVisible();

      await expect
        .poll(
          async () =>
            page.locator("iframe").evaluateAll((frames) =>
              frames.map((frame) => frame.getAttribute("src") || ""),
            ),
          { timeout: 30_000, message: "host should mount the separate-origin sandbox iframe" },
        )
        .toContainEqual(expect.stringContaining("localhost:3457"));

      let sandboxFrame = null;
      await expect
        .poll(
          () => {
            sandboxFrame = page
              .frames()
              .find((frame) => frame.url().startsWith("http://localhost:3457"));
            return Boolean(sandboxFrame);
          },
          { timeout: 30_000, message: "sandbox frame should load on :3457" },
        )
        .toBe(true);

      expect(new URL(page.url()).origin).toBe("http://localhost:3456");
      expect(new URL(sandboxFrame.url()).origin).toBe("http://localhost:3457");

      let appFrame = null;
      await expect
        .poll(
          () => {
            appFrame = sandboxFrame.childFrames()[0] || null;
            return Boolean(appFrame);
          },
          { timeout: 30_000, message: "sandbox should create the inner MCP App iframe" },
        )
        .toBe(true);

      await expect
        .poll(
          async () =>
            appFrame.evaluate(() => document.documentElement?.innerHTML?.length || 0),
          { timeout: 30_000, message: "real ui:// HTML should be written into the inner iframe" },
        )
        .toBeGreaterThan(500);

      const innerHtml = await appFrame.evaluate(() => document.documentElement.outerHTML);
      expect(innerHtml.toLowerCase()).toContain("map");

      const fatalDiagnostics = diagnostics.filter((line) =>
        [
          "Timed out waiting for sandbox proxy iframe to be ready",
          "Embedding domain not allowed",
          "The sandbox is not setup securely",
          "MCPAppToolCallRouter: listTools failed",
          "MCPAppToolCallRouter: readResource failed",
        ].some((needle) => line.includes(needle)),
      );
      expect(fatalDiagnostics, diagnostics.join("\n")).toEqual([]);
    } finally {
      if (context) await context.close();
      if (skillId) {
        await authedApi(token, `/api/skills/${skillId}`, { method: "DELETE" }).catch(() => {});
      }
      if (serverCreated) {
        await authedApi(token, `/api/admin/mcp-servers/${SERVER_ID}`, { method: "DELETE" }).catch(() => {});
      }
    }
  });
});
