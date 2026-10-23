// Real production frontend/JWT/PostgreSQL APIs. Synthetic account and content;
// no intercepted responses and no external model call in this test.
const { test, expect } = require("@playwright/test");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";

test("v3 任务筛选、报告编辑恢复、授权下载和配置向导", async ({ browser }, info) => {
  test.setTimeout(180_000);
  const tag = process.env.SESSION_SEARCH_E2E_RUN_ID;
  expect(tag).toBeTruthy();
  const loginResponse = await fetch(`${BACKEND}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL, password: process.env.SELFHOST_ADMIN_PASSWORD }) });
  expect(loginResponse.ok).toBe(true);
  const login = await loginResponse.json();
  const api = async (path, method = "GET", body) => fetch(`${BACKEND}${path}`, { method, headers: { authorization: `Bearer ${login.access_token}`, "content-type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const session = `${tag}-match-24`;
  const source = `照明能耗 ${tag} 24`;
  const title = `成果报告 ${tag}`;
  const payload = { message_id: `v3-report-${tag}`, title, content: "用于远端验收的初始报告正文。", expected_revision: 0 };
  const first = await api(`/api/sessions/${session}/reports`, "POST", payload);
  expect(first.ok).toBe(true);
  const saved = await first.json();
  expect((await api(`/api/sessions/${session}/reports`, "POST", payload)).status).toBe(409);
  const context = await browser.newContext({ reducedMotion: "reduce", acceptDownloads: true });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  const page = await context.newPage();
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  try {
    await page.goto(`${FRONTEND}/workspace`);
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--primary").trim())).toBe("210 100% 40%");
    expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily)).toContain("-apple-system");
    await page.getByRole("button", { name: "待确认 / 补充", exact: true }).click();
    await expect(page.getByRole("heading", { name: source, exact: true })).toBeVisible();
    await page.goto(`${FRONTEND}/results`);
    await page.getByRole("searchbox").fill(source);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await page.getByRole("button", { name: "编辑并保存报告", exact: true }).click();
    const editor = page.getByRole("region", { name: "报告编辑器" });
    await expect(editor.getByLabel("报告正文", { exact: true })).toBeEnabled();
    await editor.getByLabel("报告正文", { exact: true }).fill("远端编辑后保存的报告正文。");
    await editor.getByRole("button", { name: "保存报告", exact: true }).click();
    await expect(editor.getByRole("status")).toContainText("报告已保存");
    const [download] = await Promise.all([page.waitForEvent("download"), editor.getByRole("button", { name: "下载已保存 TXT", exact: true }).click()]);
    expect(download.suggestedFilename()).toBe(`${title}.txt`);
    const content = await (await api(`/api/sessions/${session}/reports/${saved.report_id}/download`)).text();
    expect(content).toBe("远端编辑后保存的报告正文。");
    await page.reload();
    await page.getByRole("searchbox").fill(source); await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByRole("button", { name: "编辑并保存报告", exact: true }).click();
    await expect(page.getByLabel("报告正文", { exact: true })).toHaveValue(content);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 950 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`v3-report-${width}.png`), fullPage: true });
    }
    await page.goto(`${FRONTEND}/setup`);
    await expect(page.getByRole("heading", { name: "配置向导", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "4 验证配置", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Agent 就绪清单", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "前往对话验证", exact: true })).toHaveAttribute("href", "/chat/root-agent");
    expect(errors).toEqual([]);
  } finally { await context.close(); }
});
