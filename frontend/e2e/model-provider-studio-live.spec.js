const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");

const FRONTEND_URL = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND_URL = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
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

test.describe("dynamic model -> Skill Studio live acceptance", () => {
  test.setTimeout(120_000);

  test("discovers a database-backed model in Studio and persists the selection", async ({ browser }) => {
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

    try {
      const provider = await putJson(token, `/api/admin/model-providers/${PROVIDER_ID}`, {
        name: "Skill Studio CI Provider",
        kind: "openai-compatible",
        base_url: "http://model-provider.invalid/v1",
        api_key_ref: "${OPENAI_API_KEY}",
        enabled: true,
      });
      providerCreated = true;
      expect(provider.provider_id).toBe(PROVIDER_ID);
      expect(provider.has_api_key).toBe(true);

      const model = await putJson(token, `/api/admin/model-providers/models/${MODEL_ID}`, {
        api_name: "ci-studio-model",
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
      await page.goto(`${FRONTEND_URL}/skills/studio/${skillId}`, { waitUntil: "domcontentloaded" });

      await expect(page.getByText(/Skill Studio 已禁用|Skill Studio is disabled/i)).toHaveCount(0);

      const modelSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(modelSelect).toBeVisible({ timeout: 30_000 });
      await expect(modelSelect).toHaveValue("smart");
      await expect(modelSelect.locator(`option[value="${MODEL_ID}"]`)).toHaveCount(1);

      await modelSelect.selectOption(MODEL_ID);
      await expect(modelSelect).toHaveValue(MODEL_ID);

      const saveButton = page.getByRole("button", { name: /^(Save|保存)$/ }).first();
      await expect(saveButton).toBeEnabled();
      await saveButton.click();
      await expect(page.getByText(/^(Saved\.|已保存。)$/)).toBeVisible({ timeout: 30_000 });

      const persisted = await authedApi(token, `/api/skills/${skillId}`);
      expect(persisted.skillMetadata?.model).toBe(MODEL_ID);

      await page.reload({ waitUntil: "domcontentloaded" });
      const reloadedSelect = page.locator(`select:has(option[value="${MODEL_ID}"])`).first();
      await expect(reloadedSelect).toBeVisible({ timeout: 30_000 });
      await expect(reloadedSelect).toHaveValue(MODEL_ID);
    } finally {
      if (context) await context.close();
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
