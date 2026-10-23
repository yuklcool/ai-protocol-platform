// Production frontend + JWT/PostgreSQL + real ADK/callback/A2UI stream.
// The HTTP model is deterministic: this validates protocol wiring, not LLM quality.
const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";

test("业务计划经真实工具链创建、原位更新、刷新恢复与三档布局", async ({ browser }, info) => {
  test.setTimeout(150_000);
  test.skip(Boolean(process.env.REAL_PROVIDER_BASE_URL), "本用例使用确定性 HTTP 协议模型,不验证外部模型行为");
  const response = await fetch(`${BACKEND}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password: process.env.SELFHOST_ADMIN_PASSWORD }) });
  expect(response.ok).toBe(true);
  const login = await response.json();
  const api = async (path, method = "GET", body) => {
    const result = await fetch(`${BACKEND}${path}`, { method, headers: { authorization: `Bearer ${login.access_token}`, "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!result.ok) throw new Error(`${method} ${path}: ${result.status} ${await result.text()}`);
    return result.status === 204 ? null : result.json();
  };
  const original = await api("/api/admin/platform-config");
  const tag = randomUUID().slice(0, 8), provider = `plan-service-${tag}`, model = `plan-model-${tag}`, session = `task-plan-${tag}`;
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  let providerCreated = false, modelCreated = false, rootChanged = false, sessionCreated = false;
  try {
    await api(`/api/admin/model-providers/${provider}`, "PUT", { name: "计划协议验收", kind: "openai-compatible", base_url: "http://model-setup-probe:8080/v1", api_key_ref: "${OPENAI_API_KEY}", enabled: true }); providerCreated = true;
    await api(`/api/admin/model-providers/models/${model}`, "PUT", { api_name: "setup-chat", provider_id: provider, tier: "default", context_window: 32000, max_output_tokens: 2048, supports_tools: true, supports_responses_api: false, supports_reasoning: false, residency: "global", enabled: true }); modelCreated = true;
    for (const mode of ["completion", "tool_call"]) expect((await api(`/api/admin/model-providers/models/${model}/test`, "POST", { mode })).ok).toBe(true);
    await api("/api/admin/platform-config", "PUT", { agent: { ...original.agent, model, skills: [], tools: ["update_task_plan"], mcpServers: [], instructions: "报告公开业务步骤。", interaction: { ...original.agent.interaction, a2uiEnabled: false } } }); rootChanged = true;
    await api(`/api/sessions/${session}/bootstrap`, "POST", { skill_id: "root-agent", document_ids: [] }); sessionCreated = true;
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let streamRequests = 0;
    page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/api/agent/stream")) streamRequests++; });
    await page.goto(`${FRONTEND}/chat/root-agent?session=${session}`);
    const composer = page.locator("textarea").first();
    const send = async (text) => {
      await expect(composer).toBeEnabled({ timeout: 30_000 });
      const pending = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/api/agent/stream"));
      await composer.fill(text); await composer.press("Enter");
      const stream = await pending;
      expect(stream.ok()).toBe(true);
      const wire = await stream.text();
      expect(wire).toContain("A2UI_SURFACE"); expect(wire).toContain("update_task_plan");
      expect(wire).toContain("RUN_FINISHED"); expect(wire).not.toMatch(/"type"\s*:\s*"RUN_ERROR"/);
      return wire;
    };
    await send(`TASK-PLAN-CREATE-${tag}`);
    const cards = page.locator('[data-chat-form^="task_plan:"]');
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText("已完成 0/2 步");
    const firstNode = await cards.first().elementHandle();
    const saved = (await api(`/api/sessions/${session}/messages`)).a2ui_surfaces.find(s => s.artifact?.kind === "task-plan");
    expect(saved?.artifact.displayOnly).toBe(true);
    const updatedWire = await send(`TASK-PLAN-UPDATE-${tag}`);
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText("已完成 1/2 步");
    await expect(cards.first()).toContainText("待补充");
    await expect(cards.first()).toContainText("请补充统计日期");
    expect(await firstNode.evaluate(node => node.isConnected)).toBe(true);
    const updated = (await api(`/api/sessions/${session}/messages`)).a2ui_surfaces.find(s => s.artifact?.kind === "task-plan");
    expect(updated.surfaceId).toBe(saved.surfaceId); expect(updated.createdAt).toBe(saved.createdAt);
    await page.reload();
    await expect(cards.first()).toContainText("已完成 1/2 步");
    await expect(cards.first()).toContainText("资料检查计划");
    await expect(cards.first()).not.toHaveAttribute("data-submitted");
    expect(streamRequests).toBe(2);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(cards.first()).toBeVisible(); await expect(composer).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const path = info.outputPath(`task-plan-${width}.png`);
      await page.screenshot({ path, fullPage: true });
      await info.attach(`task-plan-${width}`, { path, contentType: "image/png" });
    }
    await info.attach("task-plan-protocol-evidence.json", { body: JSON.stringify({ surfaceId: saved.surfaceId, originalCreatedAt: saved.createdAt, updatedCreatedAt: updated.createdAt, streamRequests, emitted: updatedWire.includes("A2UI_SURFACE"), provider: "deterministic-http-fixture" }, null, 2), contentType: "application/json" });
    expect(errors).toEqual([]);
  } finally {
    await context.close();
    // Attempt every cleanup even if an earlier one fails; no external messages.
    const cleanupErrors = [];
    const clean = async (path, method, body) => { try { await api(path, method, body); } catch (error) { cleanupErrors.push(String(error)); } };
    if (rootChanged) await clean("/api/admin/platform-config", "PUT", { agent: original.agent });
    if (sessionCreated) await clean(`/api/sessions/${session}`, "DELETE");
    if (modelCreated) await clean(`/api/admin/model-providers/models/${model}`, "DELETE");
    if (providerCreated) await clean(`/api/admin/model-providers/${provider}`, "DELETE");
    expect(cleanupErrors).toEqual([]);
  }
});
