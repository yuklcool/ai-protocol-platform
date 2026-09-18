const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");

const FRONTEND_URL = process.env.PROVIDER_E2E_FRONTEND_URL || "http://localhost:3456";
const BACKEND_URL = process.env.PROVIDER_E2E_BACKEND_URL || "http://127.0.0.1:1956";
const ADMIN_EMAIL = process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com";
const ADMIN_PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD || "";
const PROVIDER_BASE_URL = (process.env.REAL_PROVIDER_BASE_URL || "").replace(/\/$/, "");
const MODEL_API_NAME = process.env.REAL_PROVIDER_MODEL || "";
const MODEL_SUPPORTS_REASONING = process.env.REAL_PROVIDER_SUPPORTS_REASONING === "true";
const RUN_ID = (process.env.PROVIDER_E2E_RUN_ID || `${Date.now()}`)
  .toLowerCase()
  .replace(/[^a-z0-9-]/g, "-")
  .slice(0, 20) + `-${randomUUID().slice(0, 8)}`;

const PROVIDER_ID = `real-e2e-${RUN_ID}`;
const MODEL_ID = `real-e2e-model-${RUN_ID}`;
// Never overwrite/delete a pre-existing MCP configuration during acceptance.
const SERVER_ID = `real-e2e-map-${RUN_ID}`;
const UPSTREAM_URL = "http://mcp-example-map:8080/mcp";
const SESSION_KEY = "aitana:local_jwt_session";
const FINAL_MARKER = "AGENT-MCP-E2E-PASS";

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

function putJson(token, path, body) {
  return authedApi(token, path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

function postJson(token, path, body) {
  return authedApi(token, path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

test.describe("real Provider -> Agent -> MCP Tool Calling acceptance", () => {
  test.setTimeout(180_000);

  test("real model selects and executes the bound MCP tool in the product chat path", async ({ browser }) => {
    expect(ADMIN_PASSWORD, "SELFHOST_ADMIN_PASSWORD must be configured").not.toBe("");
    expect(PROVIDER_BASE_URL, "REAL_PROVIDER_BASE_URL must be configured").not.toBe("");
    expect(MODEL_API_NAME, "REAL_PROVIDER_MODEL must be configured").not.toBe("");

    const login = await api("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    const token = login.access_token;
    expect(token).toBeTruthy();
    expect(login.user?.groupTags || []).toContain("aitana-admin");

    let skillId = null;
    let serverCreated = false;
    let modelCreated = false;
    let providerCreated = false;
    let context = null;

    try {
      const provider = await putJson(token, `/api/admin/model-providers/${PROVIDER_ID}`, {
        name: "Real Provider E2E",
        kind: "openai-compatible",
        base_url: PROVIDER_BASE_URL,
        api_key_ref: "${OPENAI_API_KEY}",
        enabled: true,
      });
      providerCreated = true;
      expect(provider.provider_id).toBe(PROVIDER_ID);
      expect(provider.has_api_key).toBe(true);

      const providerProbe = await postJson(token, `/api/admin/model-providers/${PROVIDER_ID}/test`);
      expect(providerProbe.ok, JSON.stringify(providerProbe)).toBe(true);

      const model = await putJson(token, `/api/admin/model-providers/models/${MODEL_ID}`, {
        api_name: MODEL_API_NAME,
        provider_id: PROVIDER_ID,
        tier: "default",
        context_window: 32_000,
        max_output_tokens: 2_048,
        description: "Ephemeral real-provider acceptance model",
        supports_tools: true,
        supports_reasoning: MODEL_SUPPORTS_REASONING,
        supports_responses_api: false,
        supports_vision: false,
        residency: "global",
        enabled: true,
      });
      modelCreated = true;
      expect(model.model_id).toBe(MODEL_ID);

      const completionProbe = await postJson(
        token,
        `/api/admin/model-providers/models/${MODEL_ID}/test`,
        { mode: "completion", prompt: "Reply with the word OK only." },
      );
      expect(completionProbe.ok, JSON.stringify(completionProbe)).toBe(true);
      expect(String(completionProbe.content || "").trim().length).toBeGreaterThan(0);

      const toolProbe = await postJson(
        token,
        `/api/admin/model-providers/models/${MODEL_ID}/test`,
        { mode: "tool_call", prompt: "Call the provided platform_probe tool now." },
      );
      expect(toolProbe.ok, JSON.stringify(toolProbe)).toBe(true);
      expect(toolProbe.tool_called).toBe(true);

      await putJson(token, `/api/admin/mcp-servers/${SERVER_ID}`, {
        url: UPSTREAM_URL,
        transport: "streamable-http",
        scope: "platform",
        enabled: true,
        description: "real Provider -> Agent -> MCP acceptance",
      });
      serverCreated = true;

      const mcpHealth = await postJson(token, `/api/admin/mcp-servers/${SERVER_ID}/health`);
      expect(mcpHealth.ok, JSON.stringify(mcpHealth)).toBe(true);
      const discovery = await postJson(token, `/api/admin/mcp-servers/${SERVER_ID}/discover`);
      expect(discovery.ok, JSON.stringify(discovery)).toBe(true);
      expect(discovery.tools?.some((tool) => tool.name === "show-map")).toBe(true);

      const skill = await authedApi(token, "/api/skills", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: `real-provider-mcp-${RUN_ID}`,
          description: "Real Provider Agent MCP acceptance skill",
          instructions:
            `When the user asks for a map, you MUST call the available show-map MCP tool before answering. Never claim a map was shown unless the tool succeeded. After a successful map tool call, include the exact marker ${FINAL_MARKER} in your final answer.`,
          displayName: "Real Provider MCP Acceptance",
          accessControl: { type: "private" },
          skillMetadata: {
            model: "smart",
            thinking: "off",
            enableConfirmation: false,
            toolConfigs: { mcp: { servers: [SERVER_ID] } },
          },
        }),
      });
      skillId = skill.skillId;
      expect(skillId).toBeTruthy();

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

      // Prove the product authoring path can discover and persist the dynamic
      // database-backed model before exercising it in chat. The Skill starts on
      // a managed tier so this is a real UI selection transition, not merely a
      // read-only assertion of an API-created model id.
      await page.goto(`${FRONTEND_URL}/skills/studio/${skillId}`, { waitUntil: "domcontentloaded" });
      const modelSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(modelSelect).toBeVisible({ timeout: 30_000 });
      await expect(modelSelect).toHaveValue("smart");
      await expect(modelSelect.locator(`option[value="${MODEL_ID}"]`)).toHaveCount(1);
      await modelSelect.selectOption(MODEL_ID);
      await expect(modelSelect).toHaveValue(MODEL_ID);

      const saveButton = page.getByRole("button", { name: /^(Save|保存)$/ }).first();
      await expect(saveButton).toBeEnabled();
      await saveButton.click();
      await expect(page.getByText(/^(Saved\\.|已保存。)$/)).toBeVisible({ timeout: 30_000 });

      const persistedSkill = await authedApi(token, `/api/skills/${skillId}`);
      expect(persistedSkill.skillMetadata?.model).toBe(MODEL_ID);

      await page.goto(`${FRONTEND_URL}/chat/${skillId}`, { waitUntil: "domcontentloaded" });
      const composer = page.locator('textarea[placeholder="Message…"]');
      await expect(composer).toBeVisible({ timeout: 30_000 });
      await composer.fill(
        "Use the map tool to display Munich, Germany. You must call show-map before answering. After the tool succeeds, give me a short confirmation.",
      );
      await composer.press("Enter");

      const toolName = page.getByText(/show-map/i).first();
      await expect(toolName).toBeVisible({ timeout: 90_000 });
      await expect(page.getByLabel("Success").first()).toBeVisible({ timeout: 90_000 });

      // This iframe is produced only after the real tool definition's MCP Apps
      // binding is resolved and the real ui:// resource is fetched.
      await expect
        .poll(
          async () => page.locator("iframe").count(),
          { timeout: 60_000, message: "real MCP tool result should mount an MCP App iframe" },
        )
        .toBeGreaterThan(0);

      // User text does not contain FINAL_MARKER. Restrict to assistant bubble
      // shape so the final assertion proves the real Agent continued after the
      // tool result and authored a final response rather than stopping at ToolCall.
      const assistantFinal = page
        .locator("div.flex.items-start.gap-3:not(.justify-end)")
        .filter({ hasText: FINAL_MARKER });
      await expect(assistantFinal.last()).toBeVisible({ timeout: 90_000 });
      await expect(assistantFinal.last()).toContainText(/Munich/i);

      const fatalDiagnostics = diagnostics.filter((line) =>
        [
          "MODEL_AUTH_FAILED",
          "MODEL_REQUEST_INVALID",
          "MCPAppToolCallRouter: listTools failed",
          "MCPAppToolCallRouter: readResource failed",
          "Timed out waiting for sandbox proxy iframe to be ready",
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
      if (modelCreated) {
        await authedApi(token, `/api/admin/model-providers/models/${MODEL_ID}`, { method: "DELETE" }).catch(() => {});
      }
      if (providerCreated) {
        await authedApi(token, `/api/admin/model-providers/${PROVIDER_ID}`, { method: "DELETE" }).catch(() => {});
      }
    }
  });
});
