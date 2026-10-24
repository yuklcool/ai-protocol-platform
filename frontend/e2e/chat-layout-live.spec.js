// Production frontend + real JWT/bootstrap APIs. Message/history replies below
// are explicit protocol fixtures; this checks layout, not an external Provider.
const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const sizes = [{ width: 2200, height: 1191 }, { width: 1440, height: 1000 }, { width: 768, height: 1024 }, { width: 390, height: 844 }];

async function checkLayout(page) {
  await expect(page.locator(".chat-composer textarea")).toBeInViewport();
  const layout = await page.evaluate(() => {
    const pane = document.querySelector(".chat-pane").getBoundingClientRect();
    const composer = document.querySelector(".chat-composer").getBoundingClientRect();
    const transcript = document.querySelector("[data-chat-transcript]").getBoundingClientRect();
    const scroll = document.querySelector("[data-chat-scroll]");
    return {
      footerGap: Math.abs(pane.bottom - composer.bottom),
      overlap: transcript.bottom - composer.top,
      belowViewport: composer.bottom - innerHeight,
      documentOverflow: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) - innerHeight,
      horizontalOverflow: document.documentElement.scrollWidth - innerWidth,
      scrollHeight: scroll.scrollHeight, clientHeight: scroll.clientHeight,
    };
  });
  expect(layout.footerGap).toBeLessThanOrEqual(2);
  expect(layout.overlap).toBeLessThanOrEqual(2);
  expect(layout.belowViewport).toBeLessThanOrEqual(2);
  expect(layout.documentOverflow).toBeLessThanOrEqual(2);
  expect(layout.horizontalOverflow).toBeLessThanOrEqual(2);
  expect(layout.clientHeight).toBeGreaterThan(180);
  return layout;
}

test("任务对话：底部输入、首条消息、历史恢复和长会话独立滚动（协议 fixture）", async ({ browser }, info) => {
  test.setTimeout(150_000);
  const response = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password: process.env.SELFHOST_ADMIN_PASSWORD }),
  });
  expect(response.ok).toBe(true);
  const login = await response.json();
  const headers = { "content-type": "application/json", authorization: `Bearer ${login.access_token}` };
  async function bootstrap(sessionId) {
    const result = await fetch(`${BACKEND}/api/sessions/${sessionId}/bootstrap`, {
      method: "POST", headers, body: JSON.stringify({ skill_id: "root-agent", agent_id: "root-agent", document_ids: [] }),
    });
    expect(result.ok).toBe(true);
  }
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  const page = await context.newPage();
  const errors = [];
  const streams = [];
  page.on("pageerror", error => errors.push(error.message));
  const sessionId = `layout-${randomUUID()}`;
  await bootstrap(sessionId);
  let releaseHistory;
  const historyReady = new Promise(resolve => { releaseHistory = resolve; });
  const historyUrl = `**/api/proxy/api/sessions/${sessionId}/messages`;
  const messages = Array.from({ length: 60 }, (_, index) => ({
    role: index % 2 ? "assistant" : "user",
    content: index === 0 ? "历史消息第一条" : index === 59 ? "历史消息最后一条" : `第 ${index + 1} 条记录：${"这是需要在消息区阅读的历史任务内容。".repeat(12)}`,
    timestamp: Date.now() - (60 - index) * 1000,
  }));
  await page.route(historyUrl, async route => {
    await historyReady;
    await route.fulfill({ json: { session_id: sessionId, messages } });
  });
  await page.route("**/api/proxy/api/agent/stream", async route => {
    const body = route.request().postDataJSON();
    streams.push(body);
    await bootstrap(body.threadId);
    const events = [
      { type: "RUN_STARTED", runId: "layout-run", threadId: body.threadId },
      { type: "TEXT_MESSAGE_START", messageId: "layout-answer", role: "assistant" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "layout-answer", delta: "收到，首条回复显示在当前消息区。" },
      { type: "TEXT_MESSAGE_END", messageId: "layout-answer" },
      { type: "RUN_FINISHED", runId: "layout-run", threadId: body.threadId },
    ];
    await route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join("") });
  });
  try {
    await page.goto(`${FRONTEND}/chat/root-agent`);
    const input = page.locator(".chat-composer textarea");
    await expect(input).toBeEnabled({ timeout: 30_000 });
    for (const viewport of sizes) {
      await page.setViewportSize(viewport);
      await checkLayout(page);
      // A new conversation has readable content near the top, not an empty
      // vertically centered composer card.
      const heading = page.getByRole("heading", { name: "今天想完成什么任务？" });
      await expect(heading).toBeVisible();
      const top = await heading.boundingBox();
      const transcript = await page.locator("[data-chat-transcript]").boundingBox();
      expect(top.y - transcript.y).toBeLessThan(100);
      await page.screenshot({ path: info.outputPath(`chat-empty-${viewport.width}.png`), fullPage: true });
    }
    const originalInput = await input.elementHandle();
    await input.fill("验证首条消息不会消失");
    await input.press("Enter");
    await expect(page.getByText("收到，首条回复显示在当前消息区。", { exact: true })).toBeVisible();
    expect(await originalInput.evaluate(element => element.isConnected)).toBe(true);
    expect(streams).toHaveLength(1);
    await checkLayout(page);
    await page.screenshot({ path: info.outputPath("chat-first-reply-390.png"), fullPage: true });

    await page.goto(`${FRONTEND}/chat/root-agent?session=${sessionId}`);
    await expect(page.getByText("正在加载会话消息…", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "今天想完成什么任务？" })).toHaveCount(0);
    releaseHistory();
    await expect(page.getByText("历史消息最后一条", { exact: true })).toBeInViewport();
    for (const viewport of sizes) {
      await page.setViewportSize(viewport);
      const layout = await checkLayout(page);
      expect(layout.scrollHeight).toBeGreaterThan(layout.clientHeight);
      const scroller = page.locator("[data-chat-scroll]");
      await scroller.evaluate(element => { element.scrollTop = 0; });
      await expect(page.getByText("历史消息第一条", { exact: true })).toBeInViewport();
      await expect(page.getByText("历史消息最后一条", { exact: true })).not.toBeInViewport();
      await scroller.evaluate(element => { element.scrollTop = element.scrollHeight; });
      await expect(page.getByText("历史消息最后一条", { exact: true })).toBeInViewport();
      await page.screenshot({ path: info.outputPath(`chat-history-${viewport.width}.png`), fullPage: true });
    }
    expect(streams).toHaveLength(1); // Restoring or scrolling must never run the Agent.
    await page.unroute(historyUrl);
    await page.route(historyUrl, route => route.fulfill({ status: 503, json: { detail: "history temporarily unavailable" } }));
    await page.reload();
    await expect(page.getByRole("alert").filter({ hasText: "会话消息加载失败" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "今天想完成什么任务？" })).toHaveCount(0);
    await checkLayout(page);
    await page.unroute(historyUrl);
    await page.route(historyUrl, route => route.fulfill({ json: { session_id: sessionId, messages: [], transcript_unavailable: true } }));
    await page.reload();
    await expect(page.getByTestId("transcript-unavailable")).toBeVisible();
    await expect(page.getByRole("heading", { name: "今天想完成什么任务？" })).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    releaseHistory();
    await context.close();
  }
});
