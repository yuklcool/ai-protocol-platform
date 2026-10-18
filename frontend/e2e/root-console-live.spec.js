const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");

const FRONTEND =
  process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD;
const TENANT = `console-${randomUUID().slice(0, 8)}`;
const EMAIL = `${TENANT}@example.test`;
const MEMBER_PASSWORD = `console-acceptance-${randomUUID()}`;

async function api(path, token, method = "GET", body) {
  const response = await fetch(`${BACKEND}${path}`, {
    method,
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(body ? { "content-type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const text = await response.text();
  expect(
    response.ok,
    `${method} ${path}: ${response.status} ${text}`,
  ).toBeTruthy();
  return text ? JSON.parse(text) : null;
}

async function signedContext(browser, login) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1040 },
  });
  await context.addInitScript(
    ({ token, user, expires }) => {
      sessionStorage.setItem(
        "aitana:local_jwt_session",
        JSON.stringify({ token, user, expiresAt: Date.now() + expires * 1000 }),
      );
      localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
    },
    {
      token: login.access_token,
      user: login.user,
      expires: login.expires_in || 3600,
    },
  );
  return context;
}

test("self-host console persists tenant policies, knowledge, accounts and tool rules", async ({
  browser,
}, testInfo) => {
  test.setTimeout(180_000);
  expect(PASSWORD, "Use a disposable local-JWT acceptance stack").toBeTruthy();
  const login = await api("/api/auth/login", null, "POST", {
    email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com",
    password: PASSWORD,
  });
  const token = login.access_token;
  const original = await api("/api/admin/platform-config", token);
  const context = await signedContext(browser, login);
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let memberContext;
  try {
    await page.goto(`${FRONTEND}/admin/tenants`);
    await page.getByRole("button", { name: "新建租户", exact: true }).click();
    await page.getByLabel("稳定租户 ID", { exact: true }).fill(TENANT);
    await page.getByLabel("显示名称", { exact: true }).fill("无域名验收租户");
    await page.getByLabel("LLM 额度", { exact: false }).fill("2.5");
    await page.getByRole("button", { name: "保存租户", exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "租户配置已保存" }),
    ).toBeVisible();
    await page.getByLabel("额度控制", { exact: true }).selectOption("true");
    await page
      .getByRole("button", { name: "保存 Agent 策略", exact: true })
      .click();
    await expect(
      page.getByText("租户 Agent 策略已保存。", { exact: true }),
    ).toBeVisible();
    const tenant = await api(`/api/admin/tenants/${TENANT}`, token);
    expect(tenant.domains).toEqual([]);
    expect(tenant.quota.llmBudgetUsd).toBe(2.5);
    expect(
      (await api(`/api/admin/tenant-root/${TENANT}`, token)).effective
        .budgetEnabled,
    ).toBe(true);

    await page.goto(`${FRONTEND}/admin/tool-permissions`);
    await page.getByLabel("规则类型", { exact: true }).selectOption("tenant");
    await page.getByLabel("稳定租户 ID", { exact: true }).fill(TENANT);
    await page
      .getByLabel("允许工具", { exact: false })
      .fill("search_documents");
    await page.getByRole("button", { name: "保存规则", exact: true }).click();
    await expect(
      page.getByText(`tenant:${TENANT}`, { exact: true }),
    ).toBeVisible();

    await page.goto(`${FRONTEND}/admin/users`);
    const accountForm = page
      .locator("form")
      .filter({
        has: page.getByRole("button", { name: "创建账号", exact: true }),
      });
    await accountForm.locator('input[type="email"]').fill(EMAIL);
    await page.getByLabel("初始密码", { exact: false }).fill(MEMBER_PASSWORD);
    await page.getByLabel("所属租户", { exact: true }).selectOption(TENANT);
    expect(
      await page
        .locator("form")
        .first()
        .evaluate((form) =>
          [...form.elements]
            .filter((field) => field.validity && !field.validity.valid)
            .map((field) => ({
              type: field.type,
              message: field.validationMessage,
            })),
        ),
    ).toEqual([]);
    await page.getByRole("button", { name: "创建账号", exact: true }).click();
    await expect(page.getByText("账号已创建。", { exact: true })).toBeVisible();
    await expect(page.getByLabel("初始密码", { exact: false })).toHaveValue("");
    const member = await api("/api/auth/login", null, "POST", {
      email: EMAIL,
      password: MEMBER_PASSWORD,
    });
    memberContext = await signedContext(browser, member);
    const memberPage = await memberContext.newPage();
    await memberPage.goto(`${FRONTEND}/skills`);
    await expect(memberPage.locator('a[href="/skills"]').first()).toBeVisible();
    await expect(memberPage.locator('a[href="/admin/users"]')).toHaveCount(0);
    await expect(memberPage.locator('a[href="/agent"]')).toHaveCount(0);

    // Knowledge upload uses the authenticated administrator's own tenant.
    await page.goto(`${FRONTEND}/agent`);
    await page.getByRole("button", { name: "知识", exact: true }).click();
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: `${TENANT}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from(
          "道路照明节能验收：支路按照车流量调光，节能目标百分之三十。",
        ),
      });
    const docSelect = page.getByLabel("已上传资料", { exact: true });
    await expect(
      docSelect.locator("option", { hasText: `${TENANT}.txt` }),
    ).toBeEnabled({ timeout: 45_000 });
    await docSelect.selectOption({ label: `${TENANT}.txt · parsed` });
    await page.getByLabel("使用范围", { exact: true }).selectOption("tenant");
    await page.getByRole("button", { name: "添加并选中", exact: true }).click();
    await expect(
      page.getByText("来源已创建并选中，请保存 Root Agent 设置。", {
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "保存修改", exact: true }).click();
    await expect(page.getByText("已保存", { exact: true })).toBeVisible();
    await page.getByLabel("检索问题", { exact: true }).fill("照明节能验收");
    await page.getByRole("button", { name: "检索", exact: true }).click();
    await expect(page.locator("blockquote")).toContainText("车流量调光");
    const foreign = await api(
      "/api/agent/knowledge/search",
      member.access_token,
      "POST",
      { query: "照明节能验收" },
    );
    expect(foreign.results).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath("root-knowledge-desktop.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "租户额度", exact: true }).click();
    await page
      .getByRole("checkbox", {
        name: "对所有 Root Agent 模型调用执行租户额度控制",
      })
      .check();
    await page.getByRole("button", { name: "保存修改", exact: true }).click();
    await expect
      .poll(
        async () =>
          (await api("/api/admin/platform-config", token)).agent.budgetEnabled,
      )
      .toBe(true);

    await page.goto(`${FRONTEND}/admin/analytics`);
    await expect(
      page.getByRole("heading", { name: "用量与额度" }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: testInfo.outputPath("console-usage-mobile.png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await page
      .screenshot({
        path: testInfo.outputPath("console-final.png"),
        fullPage: true,
      })
      .catch(() => {});
    await api("/api/admin/platform-config", token, "PUT", {
      agent: original.agent,
    });
    await memberContext?.close();
    await context.close();
  }
});
