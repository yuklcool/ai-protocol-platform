// Real JWT / backend metadata API / PostgreSQL search. No stream interception,
// no model calls; synthetic summaries are seeded in the isolated Compose DB.
const { test, expect } = require("@playwright/test");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";

test("服务端搜索未加载历史、日期范围、授权分页与三档布局", async ({ browser }, info) => {
  test.setTimeout(120_000);
  const tag = process.env.SESSION_SEARCH_E2E_RUN_ID;
  expect(tag).toBeTruthy();
  const response = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: process.env.SELFHOST_ADMIN_EMAIL, password: process.env.SELFHOST_ADMIN_PASSWORD }),
  });
  expect(response.ok).toBe(true);
  const login = await response.json();
  const context = await browser.newContext({ timezoneId: "Asia/Shanghai", reducedMotion: "reduce" });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, expiresAt: Date.now() + login.expires_in * 1000, user: login.user }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.goto(`${FRONTEND}/sessions`);
    const rows = page.getByRole("list", { name: "会话搜索结果" });
    await expect(rows.getByRole("listitem")).toHaveCount(20);
    await expect(rows.getByText(new RegExp(`照明能耗 ${tag}`))).toHaveCount(0);
    await page.getByRole("searchbox", { name: "搜索历史会话" }).fill(`照明能耗 ${tag}`);
    await page.getByLabel("更新时间起").fill("2026-10-20");
    await page.getByLabel("更新时间止").fill("2026-10-20");
    const firstResponse = page.waitForResponse((r) => r.url().includes("/api/sessions/search?") && new URL(r.url()).searchParams.get("q") === `照明能耗 ${tag}`);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    const result = await firstResponse;
    expect(result.ok()).toBe(true);
    expect(new URL(result.url()).searchParams.get("updated_after")).toBe("2026-10-19T16:00:00.000Z");
    expect(new URL(result.url()).searchParams.get("updated_before")).toBe("2026-10-20T16:00:00.000Z");
    await expect(rows.getByRole("listitem")).toHaveCount(20);
    await expect(rows.getByText(`照明能耗 ${tag} 24`, { exact: true })).toBeVisible();
    await expect(rows.getByText(/不可见/)).toHaveCount(0);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.getByRole("searchbox")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const screenshot = info.outputPath(`session-search-${width}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      await info.attach(`session-search-${width}`, { path: screenshot, contentType: "image/png" });
    }
    await page.getByRole("button", { name: "加载更多", exact: true }).click();
    await expect(rows.getByRole("listitem")).toHaveCount(25);
    await expect(page.getByRole("button", { name: "加载更多", exact: true })).toHaveCount(0);
    await expect(rows.getByRole("link").last()).toHaveAttribute("href", `/chat/root-agent?session=${tag}-match-00`);
    await page.getByRole("searchbox").fill(`no-match-${tag}`);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page.getByText("没有匹配的历史会话，请调整搜索条件。")).toBeVisible();
    await expect(rows.getByRole("listitem")).toHaveCount(0);
    await page.getByRole("button", { name: "重置", exact: true }).click();
    await expect(rows.getByRole("listitem")).toHaveCount(20);
    await expect(page.getByRole("searchbox")).toHaveValue("");
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
