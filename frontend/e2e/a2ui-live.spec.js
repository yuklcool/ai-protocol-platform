const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

const FRONTEND_URL = process.env.A2UI_LIVE_FRONTEND_URL || "http://localhost:3456";
const BACKEND_URL = process.env.A2UI_LIVE_BACKEND_URL || "http://127.0.0.1:1956";
const ADMIN_EMAIL = process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com";
const ADMIN_PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD || "";
const SESSION_KEY = "aitana:local_jwt_session";
const RUN_ID = (process.env.A2UI_LIVE_RUN_ID || `${Date.now()}`)
  .toLowerCase()
  .replace(/[^a-z0-9-]/g, "-")
  .slice(0, 20) + `-${randomUUID().slice(0, 8)}`;
const SESSION_ID = `a2ui-live-${RUN_ID}`;
const SKILL_NAME = `a2ui-live-${RUN_ID}`;
const ACTION_STATE_KEY = "a2ui_surface_context.workspace.lastAction";

async function api(pathname, init = {}) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, init);
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
    throw new Error(`${init.method || "GET"} ${pathname} -> ${response.status}: ${text}`);
  }
  return body;
}

async function authedApi(token, pathname, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  return api(pathname, { ...init, headers });
}

function seedSurface(userId) {
  const root = path.resolve(__dirname, "../..");
  return execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "uv",
      "run",
      "python",
      "scripts/seed_a2ui_live.py",
      "--user-id",
      userId,
      "--session-id",
      SESSION_ID,
    ],
    {
      cwd: root,
      encoding: "utf8",
      env: process.env,
    },
  );
}

test.describe("A2UI persisted surface live acceptance", () => {
  test.setTimeout(120_000);

  test("rehydrates a real surface, persists a browser action, and survives hard reload", async ({ browser }) => {
    expect(ADMIN_PASSWORD, "SELFHOST_ADMIN_PASSWORD must be configured").not.toBe("");

    const login = await api("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    const token = login.access_token;
    const userId = login.user?.uid || login.user?.userId || login.user?.id;
    expect(token).toBeTruthy();
    expect(userId, JSON.stringify(login.user)).toBeTruthy();

    let skillId = null;
    let context = null;

    try {
      const skill = await authedApi(token, "/api/skills", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: SKILL_NAME,
          displayName: "A2UI Live Acceptance",
          description: "CI-only Skill for real persisted A2UI browser acceptance",
          instructions: "This Skill exists only for deterministic A2UI browser acceptance.",
          accessControl: { type: "private" },
          skillMetadata: {
            model: "lite",
            thinking: "off",
            tools: [],
            subSkills: [],
            toolConfigs: {
              a2ui: {
                allow_surface_context_writes: true,
              },
            },
          },
        }),
      });
      skillId = skill.skillId;
      expect(skillId).toBeTruthy();

      const bootstrap = await authedApi(token, `/api/sessions/${SESSION_ID}/bootstrap`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ skill_id: skillId, document_ids: [] }),
      });
      expect(bootstrap.session_id).toBe(SESSION_ID);

      const seedOutput = seedSurface(userId);
      expect(seedOutput).toContain('"surfaceId": "workspace"');

      const history = await authedApi(token, `/api/sessions/${SESSION_ID}/messages`);
      const replay = history.a2ui_surfaces?.find((entry) => entry.surfaceId === "workspace");
      expect(replay).toBeTruthy();
      expect(replay.messages?.length).toBeGreaterThanOrEqual(3);

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
      const diagnostics = [];
      page.on("console", (msg) => diagnostics.push(`[console:${msg.type()}] ${msg.text()}`));
      page.on("pageerror", (err) => diagnostics.push(`[pageerror] ${err.message}`));

      await page.goto(`${FRONTEND_URL}/chat/${skillId}?session=${SESSION_ID}`, {
        waitUntil: "domcontentloaded",
      });

      await expect(page.getByText("A2UI Live Acceptance").first()).toBeVisible({ timeout: 30_000 });
      await expect(
        page.getByText("Rendered from persisted PostgreSQL session state").first(),
      ).toBeVisible({ timeout: 30_000 });

      const actionButton = page.getByRole("button", { name: "Persist action" }).first();
      await expect(actionButton).toBeVisible({ timeout: 30_000 });
      await actionButton.click();

      await expect
        .poll(
          async () => {
            const state = await authedApi(token, `/api/sessions/${SESSION_ID}/state`);
            return state[ACTION_STATE_KEY] || null;
          },
          { timeout: 20_000, intervals: [250, 500, 1000] },
        )
        .toMatchObject({
          name: "accept_a2ui_live",
          sourceComponentId: "action",
          context: {
            marker: "A2UI-ACTION-PERSISTED",
            source: "chromium-live-gate",
          },
        });

      // A hard browser reload must reconstruct the surface from PostgreSQL via
      // GET /api/sessions/{id}/messages -> a2ui_surfaces -> RehydrateSurfaces.
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByText("A2UI Live Acceptance").first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("button", { name: "Persist action" }).first()).toBeVisible({
        timeout: 30_000,
      });

      const fatalDiagnostics = diagnostics.filter((line) =>
        [
          "processMessages failed",
          "Catalog not found",
          "A2UI surface dispatch failed",
          "pageerror",
        ].some((needle) => line.toLowerCase().includes(needle.toLowerCase())),
      );
      expect(fatalDiagnostics, diagnostics.join("\n")).toEqual([]);
    } finally {
      if (context) await context.close();
      await authedApi(token, `/api/sessions/${SESSION_ID}`, { method: "DELETE" }).catch(() => {});
      if (skillId) {
        await authedApi(token, `/api/skills/${skillId}`, { method: "DELETE" }).catch(() => {});
      }
    }
  });
});
