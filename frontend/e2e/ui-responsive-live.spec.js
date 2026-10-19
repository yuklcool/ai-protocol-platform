// Synthetic account, real self-host API, real browser. No API responses are mocked.
const { test, expect } = require("@playwright/test");
const { provisionAdminTenant } = require("./selfhost-fixtures");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const ROUTES = [
  "/agent", "/skills", "/skills/studio/new", "/chat/root-agent", "/admin",
  "/admin/tenants", "/admin/users", "/admin/groups", "/admin/mcp-servers",
  "/admin/model-providers", "/admin/analytics", "/admin/audit", "/admin/settings",
  "/dev/a2ui", "/dev/mcp-apps", "/dev/mcp-apps/active", "/dev/mcp-apps/passive", "/group",
];
const sizes = [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}];
async function snapshot(page, info, name) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe("light");
  const overflow = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    return [document.documentElement, document.body, ...document.querySelectorAll(".console-content, .console-public, .page-container")]
      .filter(el => el.scrollWidth > (el.clientWidth || viewport) + 2)
      .map(el => ({tag:el.tagName, className:el.className, width:el.clientWidth, content:el.scrollWidth}));
  });
  expect(overflow, `${name}: page overflow`).toEqual([]);
  await page.screenshot({path:info.outputPath(`${name}.png`),fullPage:true,animations:"disabled"});
  // Small synthetic previews allow visual review through the Actions text-log API.
  if(process.env.UI_REVIEW_PREVIEW === "1" && ["1440-agent","1440-admin-model-providers","1440-chat-root-agent","390-model-service-form","390-chat-files","1440-home","390-home"].includes(name)){
    const bytes=await page.screenshot({type:"jpeg",quality:40,animations:"disabled"});
    console.log(`UI_PREVIEW:${name}:${bytes.toString("base64")}:END_UI_PREVIEW`);
  }
}
test("全站浅色主题、三种视口、手机导航和配置表单", async ({browser}, info) => {
  test.setTimeout(420_000);
  const loginResponse=await fetch(`${BACKEND}/api/auth/login`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({email:process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com",password:process.env.SELFHOST_ADMIN_PASSWORD})});
  expect(loginResponse.ok).toBe(true); const login=await loginResponse.json();
  await provisionAdminTenant(BACKEND,login);
  const context=await browser.newContext({colorScheme:"light",reducedMotion:"reduce"});
  await context.addInitScript(({login})=>{sessionStorage.setItem("aitana:local_jwt_session",JSON.stringify({token:login.access_token,expiresAt:Date.now()+login.expires_in*1000,user:login.user}));localStorage.setItem("ai-protocol-platform.locale","zh-CN");},{login});
  const page=await context.newPage(); const errors=[];page.on("pageerror",e=>errors.push(e.message));
  try {
    for(const viewport of sizes){
      await page.setViewportSize(viewport);
      for(const route of ROUTES){
        await page.goto(`${FRONTEND}${route}`);
        await expect(page.locator("main").first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        await snapshot(page,info,`${viewport.width}-${route.slice(1).replaceAll("/","-")}`);
      }
    }
    await page.setViewportSize(sizes[2]);
    await page.goto(`${FRONTEND}/admin/tenants`);
    const trigger=page.getByRole("button",{name:"打开主导航",exact:true});await trigger.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").getByRole("link",{name:"模型服务",exact:true})).toBeVisible();
    await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);await expect(trigger).toBeFocused();
    await trigger.click();await page.getByRole("dialog").getByRole("link",{name:"模型服务",exact:true}).click();
    await expect(page).toHaveURL(/\/admin\/model-providers$/);await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button",{name:"添加模型服务",exact:true}).click();
    await expect(page.getByRole("heading",{name:"添加模型服务",exact:true})).toBeFocused();
    await page.getByLabel("服务名称",{exact:true}).fill("手机配置验收服务");
    await snapshot(page,info,"390-model-service-form");
    await page.goto(`${FRONTEND}/chat/root-agent`);
    await page.getByRole("button",{name:"显示文件列表",exact:true}).click();
    await expect(page.getByRole("button",{name:"关闭文件与历史记录",exact:true})).toBeVisible();
    await snapshot(page,info,"390-chat-files");
    await page.getByRole("button",{name:"关闭文件与历史记录",exact:true}).click();
    await expect(page.locator("textarea").first()).toBeVisible();
    expect(errors).toEqual([]);
  } finally {await context.close();}
});

test("公开首页、登录错误和 OIDC 错误反馈", async ({browser}, info)=>{
  test.setTimeout(120_000);
  const context=await browser.newContext({colorScheme:"light",reducedMotion:"reduce"});
  const page=await context.newPage();
  try{
    for(const viewport of sizes){
      await page.setViewportSize(viewport);await page.goto(FRONTEND);
      await expect(page.getByTestId("sign-in-button")).toBeVisible();
      await snapshot(page,info,`${viewport.width}-home`);
      await page.getByTestId("sign-in-button").click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await snapshot(page,info,`${viewport.width}-login`);
      await page.goto(`${FRONTEND}/auth/oidc/callback?error=access_denied&error_description=登录验收错误`);
      await expect(page.getByRole("alert")).toContainText("登录验收错误");
      await snapshot(page,info,`${viewport.width}-oidc-error`);
    }
  } finally {await context.close();}
});
