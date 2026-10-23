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
const SESSION_ID = `real-e2e-chat-${RUN_ID}`;
const UPSTREAM_URL = "http://mcp-example-map:8080/mcp";
const SESSION_KEY = "aitana:local_jwt_session";
const FINAL_MARKER = "AGENT-MCP-E2E-PASS";
const ACTION_RUN_MARKER = "A2UI-ACTION-RUN-E2E-PASS";
const ACTION_SESSION_ID = `real-e2e-action-${RUN_ID}`;

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

function parseSseDataEvents(body) {
  return String(body || "")
    .split(/\n\n+/)
    .map((chunk) => chunk.trim())
    .filter((chunk) => chunk.startsWith("data:"))
    .map((chunk) => {
      const raw = chunk.slice("data:".length).trim();
      try {
        return JSON.parse(raw);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

async function expectReadableControl(locator) {
  const contrast = await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    const rgba = (color) => {
      const channels = color.match(/[\d.]+/g).map(Number);
      return [...channels.slice(0, 3), channels[3] ?? 1];
    };
    const over = (color, background) => color.slice(0, 3).map((v, i) =>
      v * color[3] + background[i] * (1 - color[3]),
    );
    // Transparent controls display their ancestors' backgrounds; treating
    // rgba(0, 0, 0, 0) as black reports unreadable text on a white composer.
    const layers = [];
    for (let node = element; node; node = node.parentElement) {
      const color = rgba(getComputedStyle(node).backgroundColor);
      layers.push(color);
      if (color[3] === 1) break;
    }
    const background = layers.reverse().reduce((base, color) => over(color, base), [255, 255, 255]);
    const foreground = over(rgba(style.color), background);
    const luminance = (color) => {
      const channels = color.map((v) => {
        const s = v / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
    };
    const a = luminance(foreground), b = luminance(background);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
  expect(contrast, "Input and button labels must remain legible in the console theme").toBeGreaterThanOrEqual(4.5);
}

test.describe("real Provider -> Agent -> MCP Tool Calling acceptance", () => {
  test.setTimeout(360_000);

  test("real model selects and executes the bound MCP tool in the product chat path", async ({ browser }, testInfo) => {
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
    let actionSkillId = null;
    let actionSessionCreated = false;
    let serverCreated = false;
    let modelCreated = false;
    let providerCreated = false;
    let sessionCreated = false;
    let context = null;
    const originalPlatform = await authedApi(token, "/api/admin/platform-config");
    let rootTouched = false;
    const uiSessionId = `real-e2e-ui-${RUN_ID}`;

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
          },
        }),
      });
      skillId = skill.skillId;
      expect(skillId).toBeTruthy();

      await putJson(token, "/api/admin/platform-config", { agent: {
        ...originalPlatform.agent, model: "smart", skills: [skillId], tools: [], mcpServers: [SERVER_ID],
        interaction: { ...originalPlatform.agent?.interaction, a2uiEnabled: true,
          allowSurfaceContextWrites: true, allowActionTriggeredRuns: true },
      } });
      rootTouched = true;

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

      // Model configuration belongs to the single Root Agent, not a Skill.
      await page.goto(`${FRONTEND_URL}/agent`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /^(Model|模型)$/ }).click();
      const modelSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(modelSelect).toBeVisible({ timeout: 30_000 });
      await expect(modelSelect).toHaveValue("smart");
      await expect(modelSelect.locator(`option[value="${MODEL_ID}"]`)).toHaveCount(1);
      await modelSelect.selectOption(MODEL_ID);
      await expect(modelSelect).toHaveValue(MODEL_ID);

      const saveButton = page.getByRole("button", { name: /^(Save changes|保存修改)$/ }).first();
      await expect(saveButton).toBeEnabled();
      await saveButton.click();
      await expect(page.getByText(/^(Saved|已保存)$/)).toBeVisible({ timeout: 30_000 });

      const persistedRoot = await authedApi(token, "/api/admin/platform-config");
      expect(persistedRoot.agent?.model).toBe(MODEL_ID);

      // Create the real user-owned session explicitly before browser chat.
      // Fresh-chat UI also bootstraps a session, but doing that asynchronously
      // while the E2E is switching from Studio to Chat introduced a race where
      // the page was still in its bootstrap state when the composer assertion
      // ran. This uses the same production bootstrap endpoint and then exercises
      // the real resumed Chat route deterministically.
      const bootstrap = await postJson(token, `/api/sessions/${SESSION_ID}/bootstrap`, {
        skill_id: skillId,
        document_ids: [],
      });
      sessionCreated = true;
      expect(bootstrap.session_id).toBe(SESSION_ID);

      await page.goto(`${FRONTEND_URL}/chat/${skillId}?session=${SESSION_ID}`, {
        waitUntil: "domcontentloaded",
      });
      // The placeholder is intentionally stateful: while skill/backend
      // readiness settles it shows "Connecting…", then switches to "Message…".
      // Select the semantic control rather than coupling the acceptance gate to
      // a transient/localized placeholder, and require it to become interactive
      // before sending the real model turn.
      const composer = page.locator("textarea").first();
      await expect(composer).toBeVisible({ timeout: 30_000 });
      await expect(composer).toBeEnabled({ timeout: 60_000 });
      await composer.fill(
        "Use the map tool to display Munich, Germany. You must call show-map before answering. After the tool succeeds, give me a short confirmation.",
      );
      await composer.press("Enter");

      // Assert the semantic MCP App binding rather than visible ToolCallChip
      // text. MCP tools may be emitted with a long server-id prefix and the
      // compact chip intentionally truncates names, while this marker is created
      // only after tools/list resolved the exact show-map UI binding and the
      // ui:// resource was fetched.
      const routedShowMap = page
        .locator('[data-testid="mcp-app-tool"][data-tool-name="show-map"]')
        .first();
      await expect(routedShowMap).toBeVisible({ timeout: 90_000 });
      await expect(routedShowMap).toHaveAttribute("data-tool-status", "success", {
        timeout: 90_000,
      });

      // This iframe is produced only after the real tool definition's MCP Apps
      // binding is resolved and the real ui:// resource is fetched.
      await expect
        .poll(
          async () => routedShowMap.locator("iframe").count(),
          { timeout: 60_000, message: "real show-map tool result should mount its MCP App iframe" },
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

      // Close the final self-host/A2UI acceptance gap with the real Provider:
      // a persisted surface action must immediately drive a real Agent/LLM turn
      // through the production surface-action-run endpoint, without a typed chat
      // message. This proves the action-triggered path is not only unit-tested.
      const actionUiMessages = [
        { version: "v0.9", createSurface: { surfaceId: "workspace", catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json" } },
        { version: "v0.9", updateComponents: { surfaceId: "workspace", components: [
          { id: "root", component: "Column", children: ["accepted"] },
          { id: "accepted", component: "Text", text: ACTION_RUN_MARKER },
        ] } },
      ];
      const actionInstructions = `When accept_real_provider_action triggers this turn, call send_a2ui_json_to_client with exactly this JSON array: ${JSON.stringify(actionUiMessages)}. Do not call other tools.`;
      const actionSkill = await authedApi(token, "/api/skills", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: `real-provider-action-${RUN_ID}`,
          displayName: "Real Provider A2UI Action Acceptance",
          description: "CI-only real Provider surface-action-run acceptance skill",
          instructions: actionInstructions,
          accessControl: { type: "private" },
          skillMetadata: {
            model: MODEL_ID,
            thinking: "off",
            enableConfirmation: false,
            tools: [],
            subSkills: [],
          },
        }),
      });
      actionSkillId = actionSkill.skillId;

      await putJson(token, "/api/admin/platform-config", { agent: {
        ...originalPlatform.agent, model: MODEL_ID, skills: [skillId, actionSkillId], tools: [], mcpServers: [SERVER_ID],
        instructions: actionInstructions,
        interaction: { ...originalPlatform.agent?.interaction, a2uiEnabled: true,
          allowSurfaceContextWrites: true, allowActionTriggeredRuns: true },
      } });
      expect(actionSkillId).toBeTruthy();

      const actionBootstrap = await postJson(token, `/api/sessions/${ACTION_SESSION_ID}/bootstrap`, {
        skill_id: actionSkillId,
        document_ids: [],
      });
      actionSessionCreated = true;
      expect(actionBootstrap.session_id).toBe(ACTION_SESSION_ID);

      const actionRunResponse = await fetch(
        `${BACKEND_URL}/api/skills/${actionSkillId}/sessions/${ACTION_SESSION_ID}/surface-action-run`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({
            surfaceId: "workspace",
            action: {
              name: "accept_real_provider_action",
              sourceComponentId: "accept-button",
              context: {
                marker: "ACTION-TRIGGER-CONTEXT",
                source: "real-provider-release-gate",
              },
            },
            forwardedProps: {
              a2ui_surface_state: {
                workspace: {
                  status: "ready",
                },
              },
            },
          }),
        },
      );
      const actionRunBody = await actionRunResponse.text();
      expect(
        actionRunResponse.status,
        `surface-action-run failed: ${actionRunResponse.status} ${actionRunBody}`,
      ).toBe(200);
      expect(actionRunResponse.headers.get("content-type") || "").toContain("text/event-stream");
      const actionRunEvents = parseSseDataEvents(actionRunBody);
      const actionRunTypes = actionRunEvents.map((event) => event.type);
      const actionRunText = actionRunEvents
        .filter((event) => event.type === "TEXT_MESSAGE_CONTENT")
        .map((event) => String(event.delta || ""))
        .join("");
      const actionRunUi = actionRunEvents
        .filter((event) => event.type === "CUSTOM" && event.name === "A2UI_SURFACE")
        .map((event) => JSON.stringify(event.value?.messages || []))
        .join("");

      expect(actionRunTypes).toContain("RUN_STARTED");
      // Updating the UI is the action-triggered prompt's preferred response.
      // Require the marker in delivered output, rather than a conversational
      // answer that the model is explicitly instructed not to produce.
      expect(actionRunText + actionRunUi, actionRunBody).toContain(ACTION_RUN_MARKER);
      expect(actionRunTypes).toContain("RUN_FINISHED");
      expect(actionRunTypes).not.toContain("RUN_ERROR");

      const actionState = await authedApi(token, `/api/sessions/${ACTION_SESSION_ID}/state`);
      expect(actionState["a2ui_surface_context.workspace.lastAction"]).toMatchObject({
        name: "accept_real_provider_action",
        sourceComponentId: "accept-button",
        context: {
          marker: "ACTION-TRIGGER-CONTEXT",
          source: "real-provider-release-gate",
        },
      });

      // Model → A2UI form → browser input → AG-UI action run → patch → reload
      // → second operation. No seeded surface and no direct action HTTP call.
      const sid = "acceptance-form";
      const uiMessages = [
        { version: "v0.9", createSurface: { surfaceId: sid, catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json" } },
        { version: "v0.9", updateComponents: { surfaceId: sid, components: [
          { id: "root", component: "Column", children: ["heading", "input", "submit", "status"] },
          { id: "heading", component: "Text", text: "Root Agent acceptance form" },
          { id: "input", component: "TextField", label: "Acceptance value", value: { path: "/formInput" } },
          { id: "submit", component: "Button", child: "submit-label", action: { event: { name: "submit_form", context: { value: { path: "/formInput" } } } } },
          { id: "submit-label", component: "Text", text: "Apply value" },
          { id: "status", component: "Text", text: { path: "/status" } },
        ] } },
        { version: "v0.9", updateDataModel: { surfaceId: sid, value: { formInput: "initial", status: "Ready for input" } } },
      ];
      await putJson(token, "/api/admin/platform-config", { agent: {
        ...originalPlatform.agent, model: MODEL_ID, skills: [], tools: [], mcpServers: [],
        instructions: `For the initial request SHOW_ACCEPTANCE_FORM call send_a2ui_json_to_client with exactly this JSON array: ${JSON.stringify(uiMessages)}. For each submit_form UI action, read lastAction.context.value from the A2UI state. Call send_a2ui_json_to_client with v0.9 updateDataModel messages on surface acceptance-form: set /status to ACCEPTED: followed immediately by the exact submitted value, and set /formInput to that value. Never recreate or delete the surface on submit. Only for the ordinary user message CONFIRM_CHAT_MODE reply CHAT_MODE_RESTORED in text without calling tools. Do not call other tools.`,
        interaction: { ...originalPlatform.agent?.interaction, defaultSurface: "chat", defaultUpdateMode: "replace",
          a2uiEnabled: true, allowSurfaceContextWrites: true, allowActionTriggeredRuns: true },
      } });
      // A resume URL must identify an existing session. Otherwise the product
      // correctly clears a missing session and starts a new UUID, and the final
      // state assertion would inspect an ID that was never used by the UI.
      // This seeds only an empty session, never an A2UI surface or model output.
      await postJson(token, `/api/sessions/${uiSessionId}/bootstrap`, {
        skill_id: "root-agent", agent_id: "root-agent", document_ids: [],
      });
      await page.goto(`${FRONTEND_URL}/chat/root-agent?session=${uiSessionId}`, { waitUntil: "domcontentloaded" });
      const uiComposer = page.locator("textarea").first();
      await expect(uiComposer).toBeEnabled({ timeout: 30_000 });
      await uiComposer.fill("SHOW_ACCEPTANCE_FORM");
      await uiComposer.press("Enter");
      const inlineForm = page.locator('[data-chat-form="acceptance-form"]');
      await expect(inlineForm).toBeVisible({ timeout: 90_000 });
      const input = inlineForm.getByRole("textbox", { name: "Acceptance value" });
      await expect(input).toBeVisible({ timeout: 90_000 });
      await expectReadableControl(input);
      await expectReadableControl(page.getByRole("button", { name: "Apply value" }));
      await expectReadableControl(uiComposer);
      expect(new URL(page.url()).searchParams.get("session")).toBe(uiSessionId);
      await input.fill("first-value");
      const actionResponse = page.waitForResponse((response) =>
        response.url().endsWith("/api/agent/stream") && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Apply value" }).click();
      const actionWire = await (await actionResponse).text();
      const actionEvents = parseSseDataEvents(actionWire);
      console.info("Root browser action events", JSON.stringify(actionEvents));
      try {
        await expect(page.getByText(/^ACCEPTED:\s*first-value$/)).toBeVisible({ timeout: 30_000 });
      } catch (error) {
        const screenshot = testInfo.outputPath("root-action-failure.png");
        await page.screenshot({ path: screenshot, fullPage: true });
        await testInfo.attach("root-action-failure", { path: screenshot, contentType: "image/png" });
        console.info("Root browser action page", await page.locator("body").innerText());
        console.info("Root browser action state", JSON.stringify(await authedApi(token, `/api/sessions/${uiSessionId}/state`)));
        console.info("Root browser diagnostics", JSON.stringify(diagnostics));
        throw error;
      }
      await expect(page.locator('[data-execution-id]')).not.toHaveCount(0);
      for (const width of [1440, 768, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await expect(inlineForm).toBeVisible();
        await expect(page.locator("textarea").first()).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const screenshot = testInfo.outputPath(`in-chat-action-${width}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        await testInfo.attach(`in-chat-action-${width}`, { path: screenshot, contentType: "image/png" });
      }
      await page.setViewportSize({ width: 1280, height: 900 });
      const firstScreenshot = testInfo.outputPath("root-action-first.png");
      await page.screenshot({ path: firstScreenshot, fullPage: true });
      await testInfo.attach("root-action-first", { path: firstScreenshot, contentType: "image/png" });
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByText(/^ACCEPTED:\s*first-value$/)).toBeVisible({ timeout: 30_000 });
      await expect(input).toHaveValue("first-value");
      await expect(page.locator("body")).not.toContainText("Respond by updating the surface.");
      await input.fill("second-value");
      await page.getByRole("button", { name: "Apply value" }).click();
      await expect(page.getByText(/^ACCEPTED:\s*second-value$/)).toBeVisible({ timeout: 90_000 });
      const finalScreenshot = testInfo.outputPath("root-action-after-reload.png");
      await page.screenshot({ path: finalScreenshot, fullPage: true });
      await testInfo.attach("root-action-after-reload", { path: finalScreenshot, contentType: "image/png" });
      const uiState = await authedApi(token, `/api/sessions/${uiSessionId}/state`);
      expect(uiState[`a2ui_surface_context.${sid}.lastAction`].context.value).toBe("second-value");
      // The action trigger is per turn: returning to the composer must clear
      // it, while retaining the durable lastAction and current surface data.
      await expect(uiComposer).toBeEnabled({ timeout: 30_000 });
      await uiComposer.fill("CONFIRM_CHAT_MODE");
      await uiComposer.press("Enter");
      await expect(page.getByText("CHAT_MODE_RESTORED", { exact: true })).toBeVisible({ timeout: 90_000 });
      const chatState = await authedApi(token, `/api/sessions/${uiSessionId}/state`);
      expect(chatState.a2ui_action_trigger).toBeNull();
      expect(chatState.a2ui_surface_state[sid].dataModel.formInput).toBe("second-value");
      expect(chatState[`a2ui_surface_context.${sid}.lastAction`].context.value).toBe("second-value");

      const fatalDiagnostics = diagnostics.filter((line) =>
        [
          "MODEL_AUTH_FAILED",
          "MODEL_REQUEST_INVALID",
          "MCPAppToolCallRouter: listTools failed",
          "MCPAppToolCallRouter: readResource failed",
          "MCPAppToolCallRouter: update-model-context POST failed",
          "Timed out waiting for sandbox proxy iframe to be ready",
        ].some((needle) => line.includes(needle)),
      );
      expect(fatalDiagnostics, diagnostics.join("\n")).toEqual([]);
    } finally {
      if (context) await context.close();
      await authedApi(token, `/api/sessions/${uiSessionId}`, { method: "DELETE" }).catch(() => {});
      if (rootTouched) await putJson(token, "/api/admin/platform-config", { agent: originalPlatform.agent });
      if (actionSessionCreated) {
        await authedApi(token, `/api/sessions/${ACTION_SESSION_ID}`, { method: "DELETE" }).catch(() => {});
      }
      if (actionSkillId) {
        await authedApi(token, `/api/skills/${actionSkillId}`, { method: "DELETE" }).catch(() => {});
      }
      if (sessionCreated) {
        await authedApi(token, `/api/sessions/${SESSION_ID}`, { method: "DELETE" }).catch(() => {});
      }
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
