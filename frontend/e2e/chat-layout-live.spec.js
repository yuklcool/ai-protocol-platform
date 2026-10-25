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

test("普通对话：底部输入、首条消息、历史恢复和长会话独立滚动（协议 fixture）", async ({ browser }, info) => {
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
      const heading = page.getByRole("heading", { name: "今天想聊些什么？" });
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
    await expect(page.locator("[data-execution-id]")).toHaveCount(0);
    await expect(page.locator(".workbench-pane-visible")).toHaveCount(0);
    await checkLayout(page);
    await page.screenshot({ path: info.outputPath("chat-first-reply-390.png"), fullPage: true });

    await page.goto(`${FRONTEND}/chat/root-agent?session=${sessionId}`);
    await expect(page.getByText("正在加载会话消息…", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "今天想聊些什么？" })).toHaveCount(0);
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
    await expect(page.getByRole("heading", { name: "今天想聊些什么？" })).toHaveCount(0);
    await checkLayout(page);
    await page.unroute(historyUrl);
    await page.route(historyUrl, route => route.fulfill({ json: { session_id: sessionId, messages: [], transcript_unavailable: true } }));
    await page.reload();
    await expect(page.getByTestId("transcript-unavailable")).toBeVisible();
    await expect(page.getByRole("heading", { name: "今天想聊些什么？" })).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    releaseHistory();
    await context.close();
  }
});

test("资源侧栏：全高列表、文件切换、统一最近会话和手机抽屉（历史协议 fixture）", async ({ browser }, info) => {
  test.setTimeout(150_000);
  const response = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password: process.env.SELFHOST_ADMIN_PASSWORD }),
  });
  expect(response.ok).toBe(true);
  const login = await response.json();
  const authorization = `Bearer ${login.access_token}`;
  async function api(path, method = "GET", body) {
    const result = await fetch(`${BACKEND}/api${path}`, {
      method, headers: { authorization, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    expect(result.ok, `${method} ${path}: ${result.status}`).toBe(true);
    return result.status === 204 ? null : result.json();
  }
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: sizes[1] });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const documents = [];
  const historyId = `sidebar-${randomUUID()}`;
  const sessions = Array.from({ length: 24 }, (_, index) => ({
    session_id: index === 0 ? historyId : `sidebar-fixture-${index}`,
    title: `${String(index + 1).padStart(2, "0")} · 项目资料分析与实施方案：核对阶段成果、待办事项及后续安排`,
    document_ids: [], skill_id: index % 2 ? "sidebar-assistant" : "root-agent",
    skill_label: index % 2 ? "报告助理" : "Root 智能体", owner_uid: login.user.uid,
    turn_count: 4, is_owner: true, archived_at: null,
    first_message_at: new Date(Date.now() - 86_400_000).toISOString(),
    last_message_at: new Date(Date.now() - (index + 1) * 60_000).toISOString(),
  }));
  const listRequests = [];
  await page.route(/\/api\/proxy\/api\/sessions(?:\?.*)?$/, route => {
    const params = new URL(route.request().url()).searchParams;
    listRequests.push(params.toString());
    const rows = params.has("skill_id") ? sessions.filter(row => row.skill_id === params.get("skill_id")) : sessions;
    return route.fulfill({ json: { sessions: params.has("cursor") ? rows.slice(16) : rows.slice(0, 16), next_cursor: !params.has("cursor") && rows.length > 16 ? "sidebar-next" : null } });
  });
  await page.route(/\/api\/proxy\/api\/sessions\/[^/]+\/messages$/, route => route.fulfill({ json: {
    session_id: historyId, messages: [{ role: "assistant", content: "侧栏历史恢复内容", timestamp: Date.now() }],
  } }));
  await page.route("**/api/proxy/api/agent/stream", async route => {
    const body = route.request().postDataJSON();
    await api(`/sessions/${body.threadId}/bootstrap`, "POST", { skill_id: "root-agent", agent_id: "root-agent", document_ids: [] });
    const events = [
      { type: "RUN_STARTED", runId: "sidebar-run", threadId: body.threadId },
      { type: "TEXT_MESSAGE_START", messageId: "sidebar-answer", role: "assistant" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "sidebar-answer", delta: "侧栏保持打开，可以继续查找资料。" },
      { type: "TEXT_MESSAGE_END", messageId: "sidebar-answer" },
      { type: "RUN_FINISHED", runId: "sidebar-run", threadId: body.threadId },
    ];
    await route.fulfill({ headers: { "content-type": "text/event-stream" }, body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join("") });
  });
  try {
    await api(`/sessions/${historyId}/bootstrap`, "POST", { skill_id: "root-agent", agent_id: "root-agent", document_ids: [] });
    const folder = await api("/folders", "POST", { name: "项目资料 · 侧栏交互验收" });
    const second = await api("/folders", "POST", { name: "参考文件 · 切换验收" });
    // Real uploads exercise folder loading and attachment persistence; only
    // long history rows and Agent replies use protocol fixtures above.
    for (let index = 0; index < 21; index++) {
      const form = new FormData();
      form.set("folder_id", index === 20 ? second.id : folder.id);
      form.set("file", new Blob([`侧栏资料 ${index + 1}\n项目预算与验收记录。`], { type: "text/plain" }), index === 20 ? "参考说明.txt" : `项目资料-${String(index + 1).padStart(2, "0")}.txt`);
      const uploaded = await fetch(`${BACKEND}/api/documents/upload`, { method: "POST", headers: { authorization }, body: form });
      expect(uploaded.ok).toBe(true);
      const document = await uploaded.json();
      documents.push(document.docId);
      expect(document.status).toBe("parsed");
    }
    await page.goto(`${FRONTEND}/chat/root-agent`);
    await expect(page.locator(".chat-composer textarea")).toBeEnabled();
    await page.locator("#chat-resource-toggle").click();
    const sidebar = page.locator("#chat-resource-sidebar");
    const files = sidebar.getByRole("tab", { name: "文件", exact: true });
    await expect(sidebar.getByRole("tab", { name: "历史对话", exact: true })).toHaveCount(0);
    const search = sidebar.getByRole("searchbox", { name: "搜索当前文件夹内的文件" });
    const folderButton = sidebar.getByRole("button", { name: /项目资料 · 侧栏交互验收/ });
    if (await folderButton.getAttribute("aria-expanded") !== "true") await folderButton.click();
    await expect(sidebar.getByText("项目资料-01.txt", { exact: true })).toBeVisible();
    await sidebar.getByRole("button", { name: /参考文件 · 切换验收/ }).click();
    await expect(sidebar.getByText("参考说明.txt", { exact: true })).toBeVisible();
    await expect(folderButton).toHaveAttribute("aria-expanded", "false");
    await expect(sidebar.getByText("暂无文件", { exact: true })).toHaveCount(0);
    await folderButton.click();
    await search.fill("项目资料-01");
    await expect(sidebar.getByText("项目资料-01.txt", { exact: true })).toBeVisible();
    await files.click();
    await expect(search).toHaveValue("项目资料-01");
    await search.fill("");

    for (const viewport of sizes) {
      await page.setViewportSize(viewport);
      await expect(sidebar).toBeVisible();
      for (const [tab, kind] of [[files, "files"]]) {
        await tab.click();
        // Crossing the mobile breakpoint mounts the modal's own file view.
        if (kind === "files") {
          await expect(folderButton).toBeVisible();
          if (await folderButton.getAttribute("aria-expanded") !== "true") await folderButton.click();
        }
        const scroll = sidebar.locator(`[data-resource-scroll="${kind}"]`);
        await expect.poll(() => scroll.evaluate(element => element.scrollHeight - element.clientHeight)).toBeGreaterThan(0);
        const geometry = await scroll.evaluate(element => ({ height: element.clientHeight, total: element.scrollHeight, bottom: element.getBoundingClientRect().bottom }));
        const bounds = await sidebar.boundingBox();
        expect(geometry.height).toBeGreaterThan(bounds.height * 0.60);
        expect(geometry.total).toBeGreaterThan(geometry.height);
        expect(bounds.y + bounds.height - geometry.bottom).toBeLessThan(kind === "files" ? 130 : 25);
        await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
        await expect(sidebar.getByRole("tablist")).toBeInViewport();
        if (viewport.width >= 768) await checkLayout(page);
        await scroll.evaluate(element => { element.scrollTop = 0; });
        await page.screenshot({ path: info.outputPath(`sidebar-${kind}-${viewport.width}.png`), fullPage: true });
      }
    }
    const dialog = page.getByRole("dialog", { name: "对话资源" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.locator("#chat-resource-toggle")).toBeFocused();
    await page.locator("#chat-resource-toggle").click();
    await page.locator(".chat-resource-overlay").click({ position: { x: 380, y: 400 } });
    await expect(dialog).toHaveCount(0);
    await page.locator("#chat-resource-toggle").click();
    await dialog.getByRole("button", { name: "关闭对话文件" }).click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: "打开主导航", exact: true }).click();
    await page.getByRole("dialog", { name: "主导航", exact: true }).getByRole("link", { name: sessions[0].title, exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(historyId));
    await expect(page.getByText("侧栏历史恢复内容", { exact: true })).toBeVisible();
    await page.locator("#chat-resource-toggle").click();
    await files.click();
    if (await folderButton.getAttribute("aria-expanded") !== "true") await folderButton.click();
    await sidebar.getByText("项目资料-01.txt", { exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "取消分析 项目资料-01.txt", exact: true })).toBeVisible();
    await expect.poll(async () => (await api(`/sessions/${historyId}/documents`)).documents.map(row => row.filename)).toContain("项目资料-01.txt");

    await page.setViewportSize(sizes[1]);
    await page.goto(`${FRONTEND}/chat/root-agent`);
    await page.locator("#chat-resource-toggle").click();
    const input = page.locator(".chat-composer textarea");
    await input.fill("打开侧栏后发送首条消息");
    await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
    await input.press("Enter");
    await expect(page.getByText("侧栏保持打开，可以继续查找资料。", { exact: true })).toBeVisible();
    await expect(sidebar).toBeVisible();
    await checkLayout(page);
    expect(errors).toEqual([]);
  } finally {
    await context.close();
    for (const id of documents) await api(`/documents/${id}`, "DELETE");
  }
});
