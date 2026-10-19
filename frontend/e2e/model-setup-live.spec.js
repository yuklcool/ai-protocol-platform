const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const { provisionAdminTenant } = require("./selfhost-fixtures");
const FRONTEND =
  process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const BASE =
  process.env.REAL_PROVIDER_BASE_URL || "http://model-setup-probe:8080/v1";
const MODEL = process.env.REAL_PROVIDER_MODEL || "setup-chat";
const REAL = !!process.env.REAL_PROVIDER_BASE_URL;
const API = "/api/admin/model-providers";

test("中文模型接入、持久化、失效重测、手机布局和 Root 实际请求", async ({
  browser,
}, info) => {
  test.setTimeout(240_000);
  const loginResponse = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com",
      password: process.env.SELFHOST_ADMIN_PASSWORD,
    }),
  });
  expect(loginResponse.ok).toBe(true);
  const login = await loginResponse.json();
  const headers = {
    authorization: `Bearer ${login.access_token}`,
    "content-type": "application/json",
  };
  const api = async (path, method = "GET", body) => {
    const response = await fetch(`${BACKEND}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    expect(response.ok, `${method} ${path}: ${response.status}`).toBe(true);
    return response.status === 204 ? null : response.json();
  };
  await provisionAdminTenant(BACKEND, login);
  const original = await api("/api/admin/platform-config");
  const originalRouting = await api("/api/admin/model-registry/settings");
  const tag = randomUUID().slice(0, 8);
  const name = `中文接入验收-${tag}`;
  const context = await browser.newContext();
  await context.addInitScript(
    (session) =>
      sessionStorage.setItem(
        "aitana:local_jwt_session",
        JSON.stringify(session),
      ),
    {
      token: login.access_token,
      expiresAt: Date.now() + login.expires_in * 1000,
      user: login.user,
    },
  );
  let providerId, modelId;
  const sessionId = `model-setup-${tag}`;
  let sessionCreated = false;
  let primaryError;
  try {
    // Isolate the existing Root's tools/instructions; the UI operation must preserve these fields.
    const agent = {
      ...original.agent,
      instructions: "按用户要求回复标记。",
      skills: [],
      tools: [],
      mcpServers: [],
    };
    await api("/api/admin/platform-config", "PUT", { agent });
    const page = await context.newPage();
    await page.goto(`${FRONTEND}/admin/model-providers`);
    await page
      .getByRole("button", { name: "添加模型服务", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "添加模型服务" }),
    ).toBeFocused();
    await page.getByLabel("服务名称", { exact: true }).fill(name);
    await page.getByLabel("服务名称", { exact: true }).press("Tab");
    await expect(page.getByLabel(/^API 根地址/)).toBeFocused();
    await page.getByLabel(/^API 根地址/).fill(BASE);
    await page.getByLabel(/^后端密钥变量名/).fill("OPENAI_API_KEY");
    await page.screenshot({
      path: info.outputPath("model-setup-service.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "保存并选择模型" }).click();
    await expect(
      page.getByRole("heading", { name: "选择模型", exact: true }),
    ).toBeVisible();
    if (!REAL) {
      await page
        .getByLabel("服务返回的模型", { exact: true })
        .selectOption(MODEL);
    } else {
      // A service may omit /models. Manual API names remain a first-class input.
      await page.getByLabel(/^服务中的模型名称/).fill(MODEL);
    }
    await page.getByText("高级：能力、限制与费用", { exact: true }).click();
    await page.getByLabel("最大输出（token）", { exact: true }).fill("2048");
    if (process.env.REAL_PROVIDER_SUPPORTS_REASONING === "true")
      await page.getByLabel("使用推理模型参数", { exact: true }).check();
    await page.screenshot({
      path: info.outputPath("model-setup-model-form.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "保存并测试", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "运行两项测试", exact: true }),
    ).toBeVisible();
    const service = (await api(API)).find((p) => p.name === name);
    providerId = service.provider_id;
    const model = (await api(`${API}/models`)).find(
      (m) => m.provider_id === providerId,
    );
    modelId = model.model_id;
    expect(modelId).toMatch(/^model-/);
    expect(providerId).toMatch(/^service-/);
    await expect(
      page.getByRole("button", { name: "用于平台 Root", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "运行两项测试" }).click();
    await expect(
      page.getByRole("button", { name: "用于平台 Root", exact: true }),
    ).toBeEnabled({ timeout: 120_000 });
    await page
      .getByRole("button", { name: "用于平台 Root", exact: true })
      .click();
    await expect(
      page.getByRole("link", { name: "开始对话", exact: true }),
    ).toBeVisible();
    expect((await api("/api/admin/platform-config")).agent).toEqual({
      ...agent,
      model: modelId,
    });
    const routing = await api("/api/admin/model-registry/settings");
    expect(routing.platform_default).toBe(originalRouting.platform_default);
    expect(routing.tier_defaults).toEqual(originalRouting.tier_defaults);
    expect(routing.source).toBe(originalRouting.source);
    await page.reload();
    await page.getByRole("heading", { name, exact: false }).waitFor();
    const card = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name, exact: false }) });
    await card.getByRole("button", { name: "测试与使用" }).click();
    await expect(
      page.getByRole("button", { name: "已用于平台 Root", exact: true }),
    ).toBeVisible();
    expect(
      (await api(`${API}/models`)).find((m) => m.model_id === modelId).readiness
        .ready,
    ).toBe(true);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("model-setup-mobile.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByRole("button", { name: "返回服务列表" }).click();
    await card.getByRole("button", { name: "编辑服务", exact: true }).click();
    await expect(page.getByLabel(/^后端密钥变量名/)).toHaveValue(
      "OPENAI_API_KEY",
    );
    await page.getByLabel(/^后端密钥变量名/).fill("MODEL_SETUP_ABSENT_KEY");
    await page.getByRole("button", { name: "保存服务", exact: true }).click();
    await card.getByRole("button", { name: "测试与使用" }).click();
    await page.getByRole("button", { name: "运行两项测试" }).click();
    await expect(
      page.getByText(/后端密钥变量不存在或为空/).first(),
    ).toBeVisible();
    expect(
      (await api(`${API}/models`)).find((m) => m.model_id === modelId).readiness
        .ready,
    ).toBe(false);
    await page.screenshot({
      path: info.outputPath("model-setup-error.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "返回服务列表" }).click();
    await card.getByRole("button", { name: "编辑服务", exact: true }).click();
    await page.getByLabel(/^后端密钥变量名/).fill("OPENAI_API_KEY");
    await page.getByRole("button", { name: "保存服务", exact: true }).click();
    await card.getByRole("button", { name: "编辑模型", exact: true }).click();
    await page.getByText("高级：能力、限制与费用", { exact: true }).click();
    await expect(
      page.getByLabel("最大输出（token）", { exact: true }),
    ).toHaveValue("2048");
    await page.getByLabel("最大输出（token）", { exact: true }).fill("2049");
    await page.getByRole("button", { name: "保存并测试", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "运行两项测试", exact: true }),
    ).toBeVisible();
    expect(
      (await api(`${API}/models`)).find((m) => m.model_id === modelId).readiness
        .ready,
    ).toBe(false);
    await page.getByRole("button", { name: "运行两项测试" }).click();
    await expect
      .poll(
        async () =>
          (await api(`${API}/models`)).find((m) => m.model_id === modelId)
            .readiness.ready,
        { timeout: 120_000 },
      )
      .toBe(true);
    await page.getByRole("link", { name: "开始对话", exact: true }).click();
    await api(`/api/sessions/${sessionId}/bootstrap`, "POST", {
      skill_id: "root-agent",
      document_ids: [],
    });
    sessionCreated = true;
    await page.goto(`${FRONTEND}/chat/root-agent?session=${sessionId}`);
    const composer = page.locator("textarea").first();
    await expect(composer).toBeEnabled({ timeout: 60_000 });
    const marker = `MODEL-SETUP-ROOT-${tag}`;
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/agent/stream") &&
        r.request().method() === "POST",
      { timeout: 90_000 },
    );
    await composer.fill(`请仅回复以下标记：${marker}`);
    await composer.press("Enter");
    const stream = await responsePromise;
    expect(stream.ok()).toBe(true);
    const body = await stream.text();
    expect(body).not.toMatch(/"type"\s*:\s*"RUN_ERROR"/);
    expect(body).toMatch(/RUN_FINISHED/);
    const assistant = page
      .locator("div.flex.items-start.gap-3:not(.justify-end)")
      .filter({ hasText: marker });
    await expect(assistant.last()).toBeVisible({ timeout: 60_000 });
    if (!REAL) {
      const evidence = await fetch("http://127.0.0.1:7956/evidence").then((r) =>
        r.json(),
      );
      expect(
        evidence.some((e) => e.model === MODEL && e.root_marker === marker),
      ).toBe(true);
      await info.attach("protocol-fixture-evidence.json", {
        body: JSON.stringify(evidence, null, 2),
        contentType: "application/json",
      });
    }
    await page.screenshot({
      path: info.outputPath("model-setup-root-chat.png"),
      fullPage: true,
    });
  } catch (error) {
    primaryError = error;
    throw error;
  } finally {
    await context.close();
    const errors = [];
    const clean = async (path, method, body) => {
      try {
        await api(path, method, body);
      } catch (error) {
        errors.push(String(error));
      }
    };
    await clean("/api/admin/platform-config", "PUT", { agent: original.agent });
    if (sessionCreated) await clean(`/api/sessions/${sessionId}`, "DELETE");
    if (modelId) await clean(`${API}/models/${modelId}`, "DELETE");
    if (providerId) await clean(`${API}/${providerId}`, "DELETE");
    if (errors.length) {
      await info.attach("cleanup-errors.txt", {
        body: errors.join("\n"),
        contentType: "text/plain",
      });
      if (!primaryError) throw new Error(errors.join("\n"));
    }
  }
});
