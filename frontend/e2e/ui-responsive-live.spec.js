// Synthetic account, real self-host API, real browser. No API responses are mocked.
const { test, expect } = require("@playwright/test");
const FRONTEND = process.env.MODEL_STUDIO_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.MODEL_STUDIO_BACKEND_URL || "http://127.0.0.1:1956";
const ROUTES = [
  "/setup", "/admin/knowledge", "/admin/diagnostics", "/settings", "/documents", "/settings/personal", "/workspace", "/sessions", "/results", "/agent", "/skills", "/skills/studio/new", "/chat/root-agent", "/admin",
   "/admin/users",  "/admin/mcp-servers",
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
  const reviewRoutes = ["results", "documents", "skills", "settings", "setup", "admin", "admin-users", "admin-model-providers", "admin-mcp-servers", "admin-knowledge", "admin-diagnostics", "admin-analytics", "skills-studio-new"];
  if(process.env.UI_REVIEW_PREVIEW === "1" && (["1440-agent","1440-chat-root-agent","390-model-service-form","390-mcp-server-form","390-chat-files","1440-home","390-home"].includes(name) || /^(1440|390)-/.test(name) && reviewRoutes.some(route => name.endsWith(`-${route}`)))){
    const bytes=await page.screenshot({type:"jpeg",quality:40,animations:"disabled"});
    console.log(`UI_PREVIEW:${name}:${bytes.toString("base64")}:END_UI_PREVIEW`);
  }
}
test("全站浅色主题、三种视口、手机导航和配置表单", async ({browser}, info) => {
  test.setTimeout(420_000);
  const loginResponse=await fetch(`${BACKEND}/api/auth/login`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({email:process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com",password:process.env.SELFHOST_ADMIN_PASSWORD})});
  expect(loginResponse.ok).toBe(true); const login=await loginResponse.json();

  const context=await browser.newContext({colorScheme:"light",reducedMotion:"reduce"});
  await context.addInitScript(({login})=>{sessionStorage.setItem("aitana:local_jwt_session",JSON.stringify({token:login.access_token,expiresAt:Date.now()+login.expires_in*1000,user:login.user}));localStorage.setItem("ai-protocol-platform.locale","zh-CN");},{login});
  const page=await context.newPage(); page.setDefaultTimeout(20_000); page.setDefaultNavigationTimeout(20_000); const errors=[];page.on("pageerror",e=>errors.push(e.message));
  const reviewServer = `ui-layout-${process.env.GITHUB_RUN_ID || Date.now()}`;
  let primaryError;
  try {
    for(const viewport of sizes){
      await page.setViewportSize(viewport);
      for(const route of ROUTES){
        console.log(`UI_ROUTE:${viewport.width}:${route}`);
        await page.goto(`${FRONTEND}${route}`);
        await expect(page.locator("main").first()).toBeVisible();
        if(route === "/chat/root-agent") await expect(page.locator("textarea").first()).toBeVisible();
        else await expect(page.getByRole("heading", {level:1}).first()).toBeVisible();
        if(route === "/setup") await expect(page.getByRole("button", {name:"添加模型服务",exact:true})).toBeVisible();
        if(["/results", "/documents", "/skills"].includes(route)) {
          const header = await page.locator(".page-header").first().boundingBox();
          expect(header.height, `${route}: compact title and action`).toBeLessThan(64);
        }
        if(route === "/results") {
          await expect(page.getByText("正在加载会话…", {exact:true})).toHaveCount(0);
          await expect(page.getByText(/正在读取成果…/)).toHaveCount(0);
        }
        if(route === "/documents") {
          const library = page.getByRole("region", {name:"资料列表",exact:true});
          await expect(page.getByRole("button", {name:"上传资料",exact:true})).toBeEnabled();
          expect((await library.boundingBox()).y, "document list starts in the first screen").toBeLessThan(300);
        }
        if(route === "/settings") await expect(page.getByRole("main").locator('a[href="/admin/settings"]')).toBeVisible();
        if(route === "/admin/users") {
          await expect(page.getByRole("table")).toBeVisible();
          await expect(page.getByLabel("新账号邮箱", {exact:true})).toBeHidden();
          await expect(page.getByRole("table").getByRole("row").nth(1)).toBeInViewport();
        }
        if(route === "/admin/mcp-servers") {
          await expect(page.getByRole("button", {name:"新增 MCP Server",exact:true})).toBeVisible();
          await expect(page.getByLabel("Server ID", {exact:true})).toHaveCount(0);
        }
        if(route === "/admin/knowledge") {
          await expect(page.getByRole("heading", {name:"生效来源",exact:true})).toBeInViewport();
          await expect(page.getByRole("button", {name:"上传资料",exact:true})).toBeHidden();
        }
        if(route === "/admin/analytics") {
          await expect(page.getByText("估算费用", {exact:true}).first()).toBeInViewport();
          const time = await page.getByLabel("用量时间范围", {exact:true}).boundingBox();
          const user = await page.getByLabel("用户用量", {exact:true}).boundingBox();
          expect(Math.abs(time.y - user.y), "usage filters share one row").toBeLessThan(2);
          await expect(page.getByRole("table", {name:"用户用量明细",exact:true})).toBeHidden();
        }
        if(route === "/admin/audit") {
          const table=page.getByRole("table");
          await expect(table.or(page.getByRole("heading",{name:"暂无审计记录",exact:true}))).toBeVisible();
        }
        await snapshot(page,info,`${viewport.width}-${route.slice(1).replaceAll("/","-")}`);
        if(route === "/admin/audit" && viewport.width < 768 && await page.getByRole("table").isVisible()) {
          const table=page.getByRole("table");
          const scroller=table.locator("..");
          await scroller.evaluate(element=>{element.scrollLeft=element.scrollWidth;});
          expect(await scroller.evaluate(element=>element.scrollLeft)).toBeGreaterThan(0);
          await expect(table.getByRole("columnheader",{name:"变更详情",exact:true})).toBeInViewport();
          await snapshot(page,info,"390-admin-audit-scrolled");
        }
      }
    }
    await page.setViewportSize(sizes[2]);
    await page.goto(`${FRONTEND}/admin/mcp-servers`);
    const addServer = page.getByRole("button", {name:"新增 MCP Server",exact:true});
    await addServer.click();
    await expect(page.getByRole("heading", {name:"新增 MCP Server",exact:true})).toBeFocused();
    await page.getByLabel("Server ID", {exact:true}).fill("mobile-layout-review");
    await snapshot(page,info,"390-mcp-server-form");
    await page.getByRole("button", {name:"关闭",exact:true}).click();
    await expect(addServer).toBeFocused();
    await expect(page.getByLabel("Server ID", {exact:true})).toHaveCount(0);
    await addServer.click();
    await page.getByLabel("Server ID", {exact:true}).fill(reviewServer);
    await page.getByLabel("URL", {exact:true}).fill("http://mcp-example-map:8080/mcp");
    await page.getByRole("button", {name:"保存 Server",exact:true}).click();
    await expect(page.getByRole("status").filter({hasText:reviewServer})).toBeVisible();
    await expect(addServer).toBeFocused();
    const serverRow = page.getByRole("article").filter({hasText:reviewServer});
    await serverRow.getByRole("button", {name:"编辑",exact:true}).click();
    await expect(page.getByLabel("Server ID", {exact:true})).toHaveValue(reviewServer);
    await page.getByRole("button", {name:"关闭",exact:true}).click();
    page.once("dialog", dialog => dialog.accept());
    await serverRow.getByRole("button", {name:"删除",exact:true}).click();
    await expect(serverRow).toHaveCount(0);
    await page.goto(`${FRONTEND}/admin/knowledge`);
    const addSource = page.locator("summary").filter({hasText:"添加知识来源"});
    await addSource.click();
    await expect(page.getByRole("button", {name:"上传资料",exact:true})).toBeEnabled();
    await expect(page.getByLabel("已上传资料", {exact:true})).toBeVisible();
    await addSource.click();
    await expect(page.getByLabel("已上传资料", {exact:true})).toBeHidden();
    await page.goto(`${FRONTEND}/admin/users`);
    const trigger=page.getByRole("button",{name:"打开主导航",exact:true});await trigger.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const drawer=page.getByRole("dialog");
    for(const name of ["对话","成果","资料","能力","设置","查看全部"]){
      await expect(drawer.getByRole("link",{name,exact:true})).toBeVisible();
    }
    await expect(drawer.getByRole("link",{name:"模型服务",exact:true})).toHaveCount(0);
    await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);await expect(trigger).toBeFocused();
    await trigger.click();await drawer.getByRole("link",{name:"设置",exact:true}).click();
    await expect(page).toHaveURL(/\/settings$/);await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("main").locator('a[href="/admin/model-providers"]').last().click();
    await expect(page).toHaveURL(/\/admin\/model-providers$/);
    await page.getByRole("button",{name:"添加模型服务",exact:true}).click();
    await expect(page.getByRole("heading",{name:"添加模型服务",exact:true})).toBeFocused();
    await page.getByLabel("服务名称",{exact:true}).fill("手机配置验收服务");
    await snapshot(page,info,"390-model-service-form");
    await page.goto(`${FRONTEND}/chat/root-agent`);
    await page.getByRole("button",{name:"打开对话文件",exact:true}).click();
    await expect(page.getByRole("dialog").getByRole("button",{name:"关闭对话文件",exact:true})).toBeVisible();
    await snapshot(page,info,"390-chat-files");
    await page.getByRole("dialog").getByRole("button",{name:"关闭对话文件",exact:true}).click();
    await expect(page.locator("textarea").first()).toBeVisible();
    expect(errors).toEqual([]);
  } catch(error) { primaryError=error; throw error; }
  finally {
    await fetch(`${BACKEND}/api/admin/mcp-servers/${encodeURIComponent(reviewServer)}`, {method:"DELETE",headers:{authorization:`Bearer ${login.access_token}`}});
    await context.close().catch(error=>{if(!primaryError) throw error;});
  }
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
      const dialog=page.getByRole("dialog");
      await dialog.getByLabel("邮箱",{exact:true}).fill("ui-invalid-login@example.test");
      await dialog.getByLabel("密码",{exact:true}).fill("invalid-ui-password");
      await dialog.getByRole("button",{name:"登录",exact:true}).click();
      await expect(dialog.getByRole("alert")).toBeVisible();
      await snapshot(page,info,`${viewport.width}-login-error`);
      await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.getByTestId("sign-in-button")).toBeFocused();
      await page.goto(`${FRONTEND}/auth/oidc/callback?error=access_denied&error_description=登录验收错误`);
      await expect(page.getByRole("main").getByRole("alert")).toContainText("登录验收错误");
      await snapshot(page,info,`${viewport.width}-oidc-error`);
    }
  } finally {await context.close();}
});
