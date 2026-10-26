// Real HTTP origin, login, uploads and session APIs; Agent replies are explicit
// AG-UI/A2UI protocol fixtures, not an external model or server Action test.
const { test, expect } = require("@playwright/test");
const FRONTEND = new URL(process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456");
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
FRONTEND.hostname = "selfhost.test";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// A loopback IP behind a non-localhost hostname remains an insecure HTTP
// origin. Do not add a crypto polyfill or a secure-origin browser override.
test.use({ launchOptions: { args: ["--host-resolver-rules=MAP selfhost.test 127.0.0.1", "--no-proxy-server"] } });

test("HTTP 自托管：登录、新会话、上传、消息和 A2UI 操作不依赖原生 randomUUID", async ({ browser }, info) => {
  test.setTimeout(120_000);
  expect(FRONTEND.protocol).toBe("http:");
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.addInitScript(() => localStorage.setItem("ai-protocol-platform.locale", "zh-CN"));
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const errors = [], requests = [];
  page.on("pageerror", error => errors.push(error.message));
  const surfaceId = "http-confirmation";
  const form = [
    { version: "v0.9", createSurface: { surfaceId, catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json" } },
    { version: "v0.9", updateComponents: { surfaceId, components: [
      { id: "root", component: "Column", children: ["input", "button"] },
      { id: "input", component: "TextField", label: "查询范围", value: { path: "/scope" } },
      { id: "label", component: "Text", text: "确认 HTTP 查询" },
      { id: "button", component: "Button", child: "label", action: { event: { name: "confirm_http_query", context: { scope: { path: "/scope" } } } } },
    ] } },
    { version: "v0.9", updateDataModel: { surfaceId, value: { scope: "昨晚" } } },
  ];
  let login;
  await page.route("**/api/proxy/api/agent/stream", async route => {
    const body = route.request().postDataJSON();
    requests.push(body);
    const bootstrap = await fetch(`${BACKEND}/api/sessions/${body.threadId}/bootstrap`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${login.access_token}` },
      body: JSON.stringify({ skill_id: "root-agent", agent_id: "root-agent", document_ids: [] }),
    });
    expect(bootstrap.ok).toBe(true);
    const turn = requests.length, runId = `http-run-${turn}`, messageId = `http-answer-${turn}`;
    const events = [
      { type: "RUN_STARTED", runId, threadId: body.threadId },
      // Missing sourceId also exercises the workspace router's UUID path.
      ...(turn === 1 ? [{ type: "CUSTOM", name: "A2UI_SURFACE", value: { surfaceId, messages: form, artifact: { kind: "elicitation", title: "HTTP 查询确认", placement: "chat" } } }] : []),
      { type: "TEXT_MESSAGE_START", messageId, role: "assistant" },
      { type: "TEXT_MESSAGE_CONTENT", messageId, delta: turn === 1 ? "HTTP 查询等待确认。" : `HTTP 第 ${turn} 次操作完成。` },
      { type: "TEXT_MESSAGE_END", messageId },
      { type: "RUN_FINISHED", runId, threadId: body.threadId },
    ];
    await route.fulfill({ headers: { "content-type": "text/event-stream" }, body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join("") });
  });
  try {
    await page.goto(`${FRONTEND.origin}/chat/root-agent`);
    const environment = await page.evaluate(() => ({
      origin: location.origin, secureContext: isSecureContext,
      randomUUID: typeof crypto.randomUUID, getRandomValues: typeof crypto.getRandomValues,
    }));
    expect(environment).toMatchObject({ secureContext: false, randomUUID: "undefined", getRandomValues: "function" });
    await info.attach("http-browser-environment", { body: JSON.stringify(environment), contentType: "application/json" });

    await page.getByTestId("sign-in-button").first().click();
    const dialog = page.getByRole("dialog");
    await dialog.locator('input[type="email"]').fill(process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com");
    await dialog.locator('input[type="password"]').fill(process.env.SELFHOST_ADMIN_PASSWORD);
    const loginResponse = page.waitForResponse(response => response.url().endsWith("/api/auth/login") && response.request().method() === "POST");
    await dialog.locator('button[type="submit"]').click();
    const response = await loginResponse;
    expect(response.status()).toBe(200);
    login = await response.json();
    const composer = page.locator(".chat-composer textarea");
    await expect(composer).toBeEnabled();

    await expect(page.getByRole("button", { name: "添加附件", exact: true })).toBeEnabled();
    await page.getByLabel("上传对话附件").setInputFiles({
      name: "http-attachment.txt", mimeType: "text/plain", buffer: Buffer.from("HTTP 部署查询样例"),
    });
    await expect(page.getByRole("checkbox", { name: "取消分析 http-attachment.txt", exact: true })).toBeVisible();
    await expect(composer).toBeEnabled();
    await composer.fill("核对 HTTP 查询");
    await composer.press("Enter");
    const card = page.locator(`[data-chat-form="${surfaceId}"]`);
    await expect(card.getByRole("textbox", { name: "查询范围", exact: true })).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0].threadId).toMatch(UUID_V4);
    expect(requests[0].messages.find(message => message.role === "user").id).toMatch(UUID_V4);

    await card.getByRole("textbox", { name: "查询范围", exact: true }).fill("昨晚到今晨");
    await card.getByRole("button", { name: "确认 HTTP 查询", exact: true }).click();
    await expect(page.getByText("HTTP 第 2 次操作完成。", { exact: true })).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(requests[1].threadId).toBe(requests[0].threadId);
    const action = requests[1].forwardedProps.a2ui_action;
    expect(action.requestId).toMatch(UUID_V4);
    expect(action.action).toMatchObject({ name: "confirm_http_query", context: { scope: "昨晚到今晨" } });
    await page.screenshot({ path: info.outputPath("http-selfhost.png"), fullPage: true });

    await page.getByRole("button", { name: "新建对话", exact: true }).click();
    await expect(page.getByRole("heading", { name: "今天想聊些什么？" })).toBeVisible();
    await composer.fill("继续验证新会话");
    await composer.press("Enter");
    await expect(page.getByText("HTTP 第 3 次操作完成。", { exact: true })).toBeVisible();
    expect(requests).toHaveLength(3);
    expect(requests[2].threadId).toMatch(UUID_V4);
    expect(requests[2].threadId).not.toBe(requests[0].threadId);
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
