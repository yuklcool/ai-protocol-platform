// Browser protocol fixture: real product frontend/JWT/session APIs, deterministic
// AG-UI/A2UI replies. This is NOT external Provider or server Action acceptance.
const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";

test("消息流中的真实组件、活动更新、确认防重与三档布局（协议 fixture）", async ({ browser }, info) => {
  test.setTimeout(120_000);
  const response = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password: process.env.SELFHOST_ADMIN_PASSWORD }),
  });
  expect(response.ok).toBe(true);
  const login = await response.json();
  const sessionId = `in-chat-${randomUUID()}`;
  const bootstrap = await fetch(`${BACKEND}/api/sessions/${sessionId}/bootstrap`, {
    method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${login.access_token}` },
    body: JSON.stringify({ skill_id: "root-agent", agent_id: "root-agent", document_ids: [] }),
  });
  expect(bootstrap.ok).toBe(true);
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const requests = [];
  const surfaceId = "in-chat-confirmation";
  const form = [
    { version: "v0.9", createSurface: { surfaceId, catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json" } },
    { version: "v0.9", updateComponents: { surfaceId, components: [
      { id: "root", component: "Column", children: ["title", "input", "button"] },
      { id: "title", component: "Text", text: "请在对话中确认分析范围" },
      { id: "input", component: "TextField", label: "分析范围", value: { path: "/scope" } },
      { id: "label", component: "Text", text: "确认继续" },
      { id: "button", component: "Button", child: "label", action: { event: { name: "confirm_scope", context: { scope: { path: "/scope" } } } } },
    ] } },
    { version: "v0.9", updateDataModel: { surfaceId, value: { scope: "本月数据" } } },
  ];
  await page.route("**/api/proxy/api/agent/stream", async (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    console.info("IN_CHAT_FIXTURE_REQUEST", JSON.stringify({ turn: requests.length, action: body.forwardedProps?.a2ui_action?.action?.name ?? null }));
    const turn = requests.length, runId = `fixture-run-${turn}`, toolCallId = `fixture-tool-${turn}`, messageId = `fixture-answer-${turn}`;
    const events = [
      { type: "RUN_STARTED", runId, threadId: body.threadId },
      { type: "CUSTOM", name: "STAGE_PROGRESS", value: { label: "正在整理资料" } },
      { type: "TOOL_CALL_START", toolCallId, toolCallName: "read_document" },
      { type: "TOOL_CALL_ARGS", toolCallId, delta: "{}" },
      { type: "TOOL_CALL_END", toolCallId },
      { type: "TOOL_CALL_RESULT", toolCallId, messageId: `result-${turn}`, content: '{"status":"returned"}' },
      ...(turn === 1 ? [{ type: "CUSTOM", name: "A2UI_SURFACE", value: { surfaceId, messages: form, sourceId: toolCallId, artifact: { kind: "elicitation", title: "分析范围确认", placement: "chat" } } }] : []),
      { type: "TEXT_MESSAGE_START", messageId, role: "assistant" },
      { type: "TEXT_MESSAGE_CONTENT", messageId, delta: turn === 1 ? "资料读取完成，请确认范围。" : "已按确认范围继续处理。" },
      { type: "TEXT_MESSAGE_END", messageId },
      { type: "RUN_FINISHED", runId, threadId: body.threadId },
    ];
    await route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("") });
  });
  try {
    await page.goto(`${FRONTEND}/chat/root-agent?session=${sessionId}`);
    const composer = page.locator("textarea").first();
    await expect(composer).toBeEnabled({ timeout: 30_000 });
    await composer.fill("分析资料并让我确认范围");
    await composer.press("Enter");
    const card = page.locator(`[data-chat-form="${surfaceId}"]`);
    const input = card.getByRole("textbox", { name: "分析范围", exact: true });
    await expect(input).toBeVisible();
    await expect(page.locator("[data-execution-id]")).toHaveCount(1);
    const originalCard = await card.elementHandle();
    await input.fill("十月资料");
    await card.getByRole("button", { name: "确认继续", exact: true }).click();
    await expect(page.getByText("已按确认范围继续处理。", { exact: true })).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(await originalCard.evaluate((element) => element.isConnected)).toBe(true);
    expect(requests[1].forwardedProps.a2ui_action.action.name).toBe("confirm_scope");
    await expect(page.locator("[data-execution-id]")).toHaveCount(2);
    // Playwright's disabled matcher targets controls, not fieldset itself.
    // Assert the native group lock AND its inherited effect on both controls.
    await expect(card.locator("fieldset")).toHaveAttribute("disabled", "");
    await expect(input).toBeDisabled();
    await expect(card.getByRole("button", { name: "确认继续", exact: true })).toBeDisabled();
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(composer).toBeVisible();
      await expect(card).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const screenshot = info.outputPath(`in-chat-fixture-${width}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      await info.attach(`in-chat-fixture-${width}`, { path: screenshot, contentType: "image/png" });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
