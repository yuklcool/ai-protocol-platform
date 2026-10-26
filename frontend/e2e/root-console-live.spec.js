const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const PASSWORD = process.env.SELFHOST_ADMIN_PASSWORD;
const EMAIL = `personal-${randomUUID().slice(0, 8)}@example.test`;
const MEMBER_PASSWORD = `acceptance-${randomUUID()}`;
async function api(path, token, method = "GET", body) {
  const response = await fetch(`${BACKEND}${path}`, { method, headers: {
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    ...(body ? { "content-type": "application/json" } : {}),
  }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const text = await response.text();
  expect(response.ok, `${method} ${path}: ${response.status} ${text}`).toBeTruthy();
  return text ? JSON.parse(text) : null;
}
async function signedContext(browser, login) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1040 } });
  await context.addInitScript(({ login }) => {
    sessionStorage.setItem("aitana:local_jwt_session", JSON.stringify({ token: login.access_token, user: login.user, expiresAt: Date.now() + login.expires_in * 1000 }));
    localStorage.setItem("ai-protocol-platform.locale", "zh-CN");
  }, { login });
  return context;
}
test("administrator and member can edit user-owned Skills and information", async ({ browser }) => {
  test.setTimeout(120_000);
  expect(PASSWORD, "Use a disposable local-JWT stack").toBeTruthy();
  const admin = await api("/api/auth/login", null, "POST", { email: process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password: PASSWORD });
  const originalAdmin = await api("/api/auth/profile", admin.access_token);
  const context = await signedContext(browser, admin);
  let memberContext;
  let skill;
  try {
    const page = await context.newPage();
    await page.goto(`${FRONTEND}/admin/users`);
    const adminRow = page.getByRole("row").filter({ hasText: admin.user.email });
    await expect(adminRow.getByRole("button", { name: "编辑个人配置" })).toBeEnabled();
    await adminRow.getByRole("button", { name: "编辑个人配置" }).click();
    await page.getByLabel("个人信息与偏好", { exact: true }).fill("Administrator personal information");
    await page.getByRole("button", { name: "保存个人配置" }).click();
    await expect(page.getByText("个人配置已保存，下次调用立即生效。")).toBeVisible();
    expect((await api("/api/auth/profile", admin.access_token)).information).toBe("Administrator personal information");
    await page.getByRole("button", { name: "关闭", exact: true }).click();
    await page.locator("summary").filter({ hasText: "创建用户" }).click();
    await page.getByLabel("新账号邮箱", { exact: true }).fill(EMAIL);
    await page.getByLabel("初始密码（至少 12 位）", { exact: true }).fill(MEMBER_PASSWORD);
    await page.getByRole("button", { name: "创建用户", exact: true }).click();
    await expect(page.getByRole("row").filter({ hasText: EMAIL })).toBeVisible();
    const member = await api("/api/auth/login", null, "POST", { email: EMAIL, password: MEMBER_PASSWORD });
    skill = await api("/api/skills", member.access_token, "POST", { name: `personal-${randomUUID().slice(0, 8)}`, displayName: "专有技能", description: "Member-owned private acceptance skill", instructions: "MEMBER-ONLY", accessControl: { type: "private" } });
    memberContext = await signedContext(browser, member);
    const memberPage = await memberContext.newPage();
    await memberPage.goto(`${FRONTEND}/settings/personal`);
    await memberPage.getByRole("checkbox", { name: "专有技能", exact: true }).check();
    await memberPage.getByLabel("个人信息与偏好", { exact: true }).fill("Member private information");
    await memberPage.getByRole("button", { name: "保存个人配置" }).click();
    await expect(memberPage.getByText("个人配置已保存，下次调用立即生效。")).toBeVisible();
    expect(await api("/api/auth/profile", member.access_token)).toEqual({ skills: [skill.skillId], information: "Member private information" });
    await memberPage.reload();
    await expect(memberPage.getByRole("checkbox", { name: "专有技能", exact: true })).toBeChecked();
    await expect(memberPage.getByLabel("个人信息与偏好", { exact: true })).toHaveValue("Member private information");
    expect((await api(`/api/agent/capabilities/${skill.skillId}`, member.access_token)).skillId).toBe(skill.skillId);
    const denied = await fetch(`${BACKEND}/api/agent/capabilities/${skill.skillId}`, { headers: { authorization: `Bearer ${admin.access_token}` } });
    expect(denied.status).toBe(404);
    await api(`/api/skills/${skill.skillId}`, member.access_token, "DELETE");
    skill = null;
  } finally {
    await api("/api/auth/profile", admin.access_token, "PUT", originalAdmin);
    await context.close();
    if (memberContext) await memberContext.close();
    // Acceptance uses a disposable stack; disable the temporary account.
    await api(`/api/admin/accounts/${encodeURIComponent(EMAIL)}`, admin.access_token, "PATCH", { disabled: true }).catch(() => {});
  }
});
