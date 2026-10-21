const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");

const FRONTEND_URL = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND_URL = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
// CI uses the existing HTTP protocol fixture, not a real external model service.
const PROVIDER_BASE_URL = process.env.REAL_PROVIDER_BASE_URL || "http://model-setup-probe:8080/v1";
const PROVIDER_MODEL = process.env.REAL_PROVIDER_MODEL || "setup-chat";
const ADMIN_EMAIL = process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com";
const ADMIN_PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD || "";
const SESSION_KEY = "aitana:local_jwt_session";
const RUN_ID = (process.env.MODEL_STUDIO_E2E_RUN_ID || `${Date.now()}`)
  .toLowerCase()
  .replace(/[^a-z0-9-]/g, "-")
  .slice(0, 20) + `-${randomUUID().slice(0, 8)}`;

const PROVIDER_ID = `studio-e2e-${RUN_ID}`;
const MODEL_ID = `studio-e2e-model-${RUN_ID}`;

async function api(path, init = {}) {
  const response = await fetch(`${BACKEND_URL}${path}`, init);
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    throw new Error(`${init.method || "GET"} ${path} -> ${response.status}: ${text}`);
  }
  return body;
}

async function authedApi(token, path, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  return api(path, { ...init, headers });
}

function putJson(token, path, body) {
  return authedApi(token, path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

test.describe("dynamic model -> Root Agent live acceptance", () => {
  test.setTimeout(240_000);

  test("persists the Root model and edits Skill content without overwriting Agent fields", async ({ browser }, testInfo) => {
    expect(ADMIN_PASSWORD, "SELFHOST_ADMIN_PASSWORD must be configured").not.toBe("");

    const login = await api("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    const token = login.access_token;
    expect(token).toBeTruthy();
    expect(login.user?.groupTags || []).toContain("aitana-admin");

    let providerCreated = false;
    let modelCreated = false;
    let skillId = null;
    let context = null;
    const originalPlatform = await authedApi(token, "/api/admin/platform-config");
    let rootTouched = false;

    try {
      const provider = await putJson(token, `/api/admin/model-providers/${PROVIDER_ID}`, {
        name: "Skill Studio CI Provider",
        kind: "openai-compatible",
        base_url: PROVIDER_BASE_URL,
        api_key_ref: "${OPENAI_API_KEY}",
        enabled: true,
      });
      providerCreated = true;
      expect(provider.provider_id).toBe(PROVIDER_ID);
      expect(provider.has_api_key).toBe(true);

      const model = await putJson(token, `/api/admin/model-providers/models/${MODEL_ID}`, {
        api_name: PROVIDER_MODEL,
        provider_id: PROVIDER_ID,
        tier: "default",
        context_window: 16_000,
        max_output_tokens: 1_024,
        description: "Dynamic model used by Skill Studio browser acceptance",
        supports_tools: true,
        supports_reasoning: false,
        supports_responses_api: false,
        supports_vision: false,
        residency: "global",
        enabled: true,
      });
      modelCreated = true;
      expect(model.model_id).toBe(MODEL_ID);

      const models = await authedApi(token, "/api/models");
      const visible = models.models?.find((entry) => entry.id === MODEL_ID);
      expect(visible).toBeTruthy();
      expect(visible.source).toBe("database");
      expect(visible.provider_id).toBe(PROVIDER_ID);

      const skill = await authedApi(token, "/api/skills", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: `studio-model-${RUN_ID}`,
          displayName: "Skill Studio Model Acceptance",
          description: "CI skill for dynamic model selection",
          instructions: "Reply concisely.",
          references: { "guide.md": "Keep this reference when saving." },
          assets: { "template.txt": "Keep this asset when saving." },
          accessControl: { type: "private" },
          skillMetadata: {
            model: "smart",
            thinking: "off",
            tools: [],
            subSkills: [],
            toolConfigs: {},
          },
        }),
      });
      skillId = skill.skillId;
      expect(skillId).toBeTruthy();

      context = await browser.newContext();
      const localJwtSession = {
        token,
        expiresAt: Date.now() + Number(login.expires_in || 3600) * 1000,
        user: login.user,
      };
      await context.addInitScript(
        ({ key, session }) => window.sessionStorage.setItem(key, JSON.stringify(session)),
        { key: SESSION_KEY, session: localJwtSession },
      );

      const page = await context.newPage();
      await putJson(token, "/api/admin/platform-config", { agent: { ...originalPlatform.agent, model: "smart" } });
      rootTouched = true;
      await page.goto(`${FRONTEND_URL}/agent`, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /^(Model|模型)$/ }).click();

      const modelSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(modelSelect).toBeVisible({ timeout: 30_000 });
      await expect(modelSelect).toHaveValue("smart");
      await expect(modelSelect.locator(`option[value="${MODEL_ID}"]`)).toHaveCount(1);

      await modelSelect.selectOption(MODEL_ID);
      await expect(modelSelect).toHaveValue(MODEL_ID);

      const saveButton = page.getByRole("button", { name: /^(Save changes|保存修改)$/ }).first();
      await expect(saveButton).toBeEnabled();
      // The generic Root save must enforce the same readiness gate as /use.
      const rejectedSave = page.waitForResponse((response) =>
        response.url().endsWith("/api/proxy/api/admin/platform-config") &&
        response.request().method() === "PUT",
      );
      await saveButton.click();
      expect((await rejectedSave).status()).toBe(422);
      await expect(page.getByRole("alert")).toContainText(/Could not save Root Agent settings\.|无法保存 Root Agent 配置。/);
      expect((await authedApi(token, "/api/admin/platform-config")).agent?.model).toBe("smart");

      for (const mode of ["completion", "tool_call"]) {
        const probe = await authedApi(token, `/api/admin/model-providers/models/${MODEL_ID}/test`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ mode }),
        });
        expect(probe.ok, `${mode}: ${probe.message || probe.category || "probe failed"}`).toBe(true);
        if (mode === "tool_call") expect(probe.tool_called).toBe(true);
      }
      const verified = (await authedApi(token, "/api/admin/model-providers/models"))
        .find((entry) => entry.model_id === MODEL_ID);
      expect(verified?.readiness?.ready).toBe(true);
      await testInfo.attach("model-readiness.json", {
        body: JSON.stringify({ model_id: MODEL_ID, readiness: verified.readiness }, null, 2),
        contentType: "application/json",
      });

      await saveButton.click();
      await expect(page.getByText(/^(Saved|已保存)$/)).toBeVisible({ timeout: 30_000 });

      const persisted = await authedApi(token, "/api/admin/platform-config");
      expect(persisted.agent?.model).toBe(MODEL_ID);

      await page.reload({ waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: /^(Model|模型)$/ }).click();
      const reloadedSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(reloadedSelect).toBeVisible({ timeout: 30_000 });
      await expect(reloadedSelect).toHaveValue(MODEL_ID);

      await page.goto(`${FRONTEND_URL}/skills/studio/${skillId}`, { waitUntil: "domcontentloaded" });
      const description = page.getByLabel(/^(Description|说明)$/);
      await expect(description).toBeVisible({ timeout: 30_000 });
      await expect(page.locator(`select:has(option[value="${MODEL_ID}"])`)).toHaveCount(0);
      await description.fill("Updated capability content");
      await page.getByRole("button", { name: /^(Save|保存)$/ }).click();
      await expect(page.getByText(/^(Saved\.|已保存。)$/)).toBeVisible({ timeout: 30_000 });
      const savedSkill = await authedApi(token, `/api/skills/${skillId}`);
      expect(savedSkill.description).toBe("Updated capability content");
      expect(savedSkill.skillMetadata?.model).toBe("smart");
      expect(savedSkill.references).toEqual({ "guide.md": "Keep this reference when saving." });
      expect(savedSkill.assets).toEqual({ "template.txt": "Keep this asset when saving." });
      await page.screenshot({ path: testInfo.outputPath("skill-content-editor.png"), fullPage: true });
    } finally {
      if (context) await context.close();
      if (rootTouched) {
        await putJson(token, "/api/admin/platform-config", { agent: originalPlatform.agent }).catch(() => {});
      }
      if (skillId) {
        await authedApi(token, `/api/skills/${skillId}`, { method: "DELETE" }).catch(() => {});
      }
      if (modelCreated) {
        await authedApi(token, `/api/admin/model-providers/models/${MODEL_ID}`, { method: "DELETE" }).catch(() => {});
      }
      if (providerCreated) {
        await authedApi(token, `/api/admin/model-providers/${PROVIDER_ID}`, { method: "DELETE" }).catch(() => {});
      }
    }
  });
});
