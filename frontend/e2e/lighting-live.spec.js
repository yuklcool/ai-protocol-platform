// Real JWT/PostgreSQL/ADK/MCP/A2UI/product UI; model and lighting data are
// explicit, deterministic fixtures. This does not prove production connectivity.
const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const { pathToFileURL } = require("node:url");
const path = require("node:path");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";

test("照明六场景真实协议闭环、追查权限、恢复与三档布局（合成数据）", async ({ browser }, info) => {
  test.setTimeout(300_000);
  const loginResponse = await fetch(`${BACKEND}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL, password: process.env.SELFHOST_ADMIN_PASSWORD }) });
  expect(loginResponse.ok).toBe(true);
  const login = await loginResponse.json();
  const apiRaw = (url, method = "GET", body) => fetch(`${BACKEND}${url}`, { method, headers: { authorization: `Bearer ${login.access_token}`, "content-type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const api = async (url, method, body) => { const response = await apiRaw(url, method, body); if (!response.ok) throw new Error(`${url} ${response.status}: ${await response.text()}`); return response.status === 204 ? null : response.json(); };
  const original = await api("/api/admin/platform-config");
  const tag = randomUUID().slice(0, 8), provider = `lighting-provider-${tag}`, model = `lighting-model-${tag}`, mcp = `lighting-mcp-${tag}`;
  const context = await browser.newContext({ acceptDownloads: true, reducedMotion: "reduce" });
  await context.addInitScript(({ login }) => { sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user })); localStorage.setItem("ai-protocol-platform.locale", "zh-CN"); }, { login });
  const sessions = [], errors = [], evidence = [];
  let createdProvider = false, createdModel = false, createdMcp = false, changedRoot = false;
  try {
    await api(`/api/admin/model-providers/${provider}`, "PUT", { name: "照明 CI 协议模型", kind: "openai-compatible", base_url: "http://model-setup-probe:8080/v1", api_key_ref: "${OPENAI_API_KEY}", enabled: true }); createdProvider = true;
    await api(`/api/admin/model-providers/models/${model}`, "PUT", { api_name: "setup-chat", provider_id: provider, tier: "default", context_window: 32000, max_output_tokens: 2048, supports_tools: true, supports_responses_api: false, supports_reasoning: false, residency: "global", enabled: true }); createdModel = true;
    for (const mode of ["completion", "tool_call"]) expect((await api(`/api/admin/model-providers/models/${model}/test`, "POST", { mode })).ok).toBe(true);
    await api(`/api/admin/mcp-servers/${mcp}`, "PUT", { url: "http://lighting-mcp:8090/mcp", transport: "http", enabled: true, description: "CI 合成照明 MCP,无生产访问" }); createdMcp = true;
    expect((await api(`/api/admin/mcp-servers/${mcp}/health`, "POST", {})).ok).toBe(true);
    const discovered = await api(`/api/admin/mcp-servers/${mcp}/discover`, "POST", {});
    expect(discovered.tools.some(tool => tool.name === "query_lighting")).toBe(true);
    const agent = { ...original.agent, model, skills: [], tools: [], mcpServers: [mcp], instructions: "使用已授权的 query_lighting 查询照明数据。结果与证据由工具给出,不猜测生产在线或保护定值。", interaction: { ...original.agent.interaction, a2uiEnabled: true, allowSurfaceContextWrites: true, allowActionTriggeredRuns: true } };
    await api("/api/admin/platform-config", "PUT", { agent }); changedRoot = true;
    const page = await context.newPage(); page.setDefaultTimeout(30_000);
    page.on("pageerror", error => errors.push(error.message));
    let requests = 0;
    page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/api/agent/stream")) requests++; });
    const result = page.locator('[data-testid="lighting-result"]:visible');
    async function openResult() { await page.getByRole("button", { name: "查看预览", exact: true }).last().click(); await expect(result).toBeVisible(); }
    async function send(scene) {
      const session = `lighting-${scene}-${tag}-${randomUUID().slice(0, 8)}`; sessions.push(session);
      await api(`/api/sessions/${session}/bootstrap`, "POST", { skill_id: "root-agent", agent_id: "root-agent", document_ids: [] });
      await page.goto(`${FRONTEND}/chat/root-agent?session=${session}`);
      const composer = page.locator("textarea").first(); await expect(composer).toBeEnabled();
      const pending = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/api/agent/stream"));
      await composer.fill(`LIGHTING-${scene}-${tag}`); await composer.press("Enter");
      const stream = await pending; expect(stream.ok()).toBe(true);
      const wire = await stream.text(); expect(wire).toContain("query_lighting"); expect(wire).toContain("A2UI_SURFACE"); expect(wire).toContain("RUN_FINISHED"); expect(wire).not.toMatch(/"type"\s*:\s*"RUN_ERROR"/);
      await openResult();
      evidence.push({ scene, session, source: "deterministic model + real MCP fixture", emitted: true });
      return session;
    }
    const sceneTitles = [["night", "整夜单灯运行"], ["lamp_alarms", "单灯报警追查"], ["rtu", "RTU 运行"], ["rtu_alarms", "RTU 报警"], ["energy_night", "能耗分析"], ["energy_week", "能耗分析"], ["energy_volatility", "能耗分析"], ["energy_saving", "能耗分析"], ["reconcile", "单灯 / RTU 能耗对账"]];
    for (const [scene, title] of sceneTitles) {
      await send(scene);
      await expect(result.getByRole("heading", { name: title, exact: true })).toBeVisible();
      await expect(result.getByTestId("lighting-provenance")).toContainText("CI 合成");
      if (scene === "lamp_alarms") await result.getByLabel("筛选状态").selectOption("all");
      await expect(result.getByTestId("lighting-row")).toHaveCount(2);
      if (scene === "rtu") {
        await result.getByLabel("筛选状态").selectOption("窗口无记录");
        await expect(result.getByTestId("lighting-row")).toHaveCount(1);
        await expect(result.getByTestId("lighting-row")).toContainText("窗口无记录");
        await result.getByLabel("筛选状态").selectOption("all");
      }
      const beforeLocal = requests;
      await result.getByLabel("搜索清单").fill("L-0348-A");
      await expect(result.getByTestId("lighting-row")).toHaveCount(1);
      const [download] = await Promise.all([page.waitForEvent("download"), result.getByRole("button", { name: "下载当前清单 CSV" }).click()]);
      expect(download.suggestedFilename()).toContain("current-list.csv");
      await result.getByLabel("搜索清单").fill("");
      expect(requests).toBe(beforeLocal);
      await result.getByRole("button", { name: "查看 L-0348-A 证据" }).click();
      const drawer = page.getByRole("dialog"); await expect(drawer).toContainText("alarm-001"); await expect(drawer).toContainText("RTU-017"); await expect(drawer).toContainText("历史证据窗");
      for (const width of [1440, 768, 390]) {
        await page.setViewportSize({ width, height: 950 });
        await expect(drawer).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`lighting-${scene}-drawer-${width}.png`), fullPage: true });
      }
      await page.keyboard.press("Escape");
      for (const width of [1440, 768, 390]) {
        await page.setViewportSize({ width, height: 950 });
        await result.evaluate(node => { node.scrollTop = 0; });
        await result.getByRole("region", { name: "照明查询表格" }).evaluate(node => { node.scrollLeft = 0; });
        await expect(result).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const composer = page.locator("textarea").first();
        if (width === 390) {
          await expect(composer).toBeHidden();
          await expect(page.locator(".chat-resource-bar")).toBeHidden();
          const heading = await result.getByRole("heading", { name: title, exact: true }).boundingBox();
          expect(heading.y).toBeLessThan(280);
          const metrics = await result.getByTestId("lighting-metrics").boundingBox();
          expect(metrics.y + metrics.height).toBeLessThan(950);
        } else {
          await expect(composer).toBeVisible();
        }
        await page.screenshot({ path: info.outputPath(`lighting-${scene}-${width}.png`), fullPage: true });
        if (width === 390) {
          await result.getByRole("button", { name: "继续提问", exact: true }).click();
          await expect(result).toBeHidden();
          await expect(composer).toBeVisible();
          await expect(composer).toBeFocused();
          await openResult();
          await result.getByRole("button", { name: "调整查询参数" }).click();
          await page.getByRole("button", { name: "放入消息草稿" }).click();
          await expect(composer).toHaveValue(/Asia\/Shanghai/);
          await expect(composer).toBeFocused();
          await composer.fill("");
          await openResult();
        }
      }
      await page.setViewportSize({ width: 1440, height: 950 });
    }
    await send("energy_night");
    const energySwitches = [];
    for (const [view, label, days] of [["week", "近 7 日日报", 7], ["volatility", "30 日上升波动", 30], ["saving", "7 日节能率", 7], ["night", "昨夜同窗口", null]]) {
      const pending = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/api/agent/stream"));
      await result.getByRole("button", { name: `查询${label}`, exact: true }).click();
      const response = await pending;
      expect(response.ok()).toBe(true);
      expect(await response.text()).toContain("A2UI_SURFACE");
      await openResult();
      await expect(result.getByRole("button", { name: `查询${label}`, exact: true })).toHaveAttribute("aria-pressed", "true");
      const observed = await (await fetch("http://127.0.0.1:7957/evidence")).json();
      const request = observed.calls.filter(call => call.intent === "energy_view").at(-1);
      expect(request.energy_view).toBe(view);
      expect(request.basis).toBe(view === "night" ? "night" : "daily");
      expect(request.report_type).toBe(view === "night" ? null : "D");
      if (days !== null) {
        expect((Date.parse(request.window.end) - Date.parse(request.window.start)) / 86400000).toBe(days);
        expect(request.window.start).toContain("T00:00:00+08:00");
        expect(request.window.end).toContain("T00:00:00+08:00");
      } else {
        expect(request.window.start).toContain("T18:00:00+08:00");
        expect(request.window.end).toContain("T07:00:00+08:00");
      }
      if (energySwitches.length) expect(request.cutoff).toBe(energySwitches[0].cutoff);
      energySwitches.push(request);
    }
    const session = await send("night");
    const saved = (await api(`/api/sessions/${session}/messages`)).a2ui_surfaces.find(surface => surface.artifact?.kind === "lighting");
    const endpoint = `/api/skills/root-agent/sessions/${session}/surface-action-run`;
    const actionBody = { requestId: randomUUID(), surfaceId: saved.surfaceId, action: { name: "run:lighting.query", context: { actionId: "circuit-row-1" } } };
    expect((await apiRaw(endpoint, "POST", { ...actionBody, action: { ...actionBody.action, context: { actionId: "circuit-row-1", rtu_id: "FORGED" } } })).status).toBe(422);
    expect((await apiRaw(endpoint, "POST", { ...actionBody, action: { ...actionBody.action, context: { actionId: "circuit-row-2" } } })).status).toBe(409);
    const beforeAction = requests;
    await result.getByRole("button", { name: "查看 L-0348-A 证据" }).click();
    const actionStream = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/api/agent/stream"));
    await page.getByRole("button", { name: "查询同回路证据", exact: true }).dblclick();
    const followup = await actionStream; expect(followup.ok()).toBe(true); expect(await followup.text()).toContain("A2UI_SURFACE");
    expect(requests).toBe(beforeAction + 1);
    const mcpEvidence = await (await fetch("http://127.0.0.1:7957/evidence")).json();
    const canonical = mcpEvidence.calls.find(call => call.intent === "compare_circuit");
    expect(canonical.device).toMatchObject({ lamp_id: "L-0348-A", rtu_id: "RTU-017", circuit_id: "2", alarm_id: "alarm-001" });
    expect(canonical.evidence_window.start).toBeTruthy(); expect(canonical.evidence_window.end).toBeTruthy();
    await page.keyboard.press("Escape");
    const beforeReload = requests; await page.reload(); await openResult();
    await expect(result).toContainText("刷新未重放查询"); expect(requests).toBe(beforeReload);
    await result.getByRole("button", { name: "调整查询参数" }).click(); await page.getByRole("button", { name: "放入消息草稿" }).click();
    await expect(page.locator("textarea").first()).toHaveValue(/Asia\/Shanghai/); expect(requests).toBe(beforeReload);
    await send("error"); await expect(result.getByRole("alert")).toContainText("合成数据源暂不可用"); await expect(result.getByTestId("lighting-metrics")).toHaveCount(0);
    await send("empty"); await expect(result).toContainText("当前范围没有记录");
    // Snapshot comparisons are evidence for human review, not pixel parity claims.
    const prototype = await context.newPage();
    await prototype.goto(pathToFileURL(path.resolve("../outputs/lighting-a2ui-2026-10-26/index.html")).href);
    for (const width of [1440, 768, 390]) { await prototype.setViewportSize({ width, height: 950 }); await prototype.screenshot({ path: info.outputPath(`lighting-design-reference-${width}.png`), fullPage: true }); }
    await prototype.close();
    await info.attach("lighting-evidence.json", { body: JSON.stringify({ productionVerified: false, scenes: evidence, energySwitches, canonical, errors }, null, 2), contentType: "application/json" });
    expect(errors).toEqual([]);
  } finally {
    await context.close();
    const failures = [];
    const clean = async (url, method, body) => { try { await api(url, method, body); } catch (error) { failures.push(String(error)); } };
    if (changedRoot) await clean("/api/admin/platform-config", "PUT", { agent: original.agent });
    for (const session of new Set(sessions)) await clean(`/api/sessions/${session}`, "DELETE");
    if (createdMcp) await clean(`/api/admin/mcp-servers/${mcp}`, "DELETE");
    if (createdModel) await clean(`/api/admin/model-providers/models/${model}`, "DELETE");
    if (createdProvider) await clean(`/api/admin/model-providers/${provider}`, "DELETE");
    expect(failures).toEqual([]);
  }
});
