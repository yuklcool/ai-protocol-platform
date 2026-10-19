// Real browser + PostgreSQL + object volume. No model response is mocked.
const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const path = require("node:path");
const { provisionAdminTenant } = require("./selfhost-fixtures");
const FRONTEND = process.env.PROVIDER_E2E_FRONTEND_URL || "http://localhost:3456";
const BACKEND = process.env.PROVIDER_E2E_BACKEND_URL || "http://127.0.0.1:1956";
const REAL = Boolean(process.env.REAL_PROVIDER_BASE_URL && process.env.REAL_PROVIDER_MODEL);
const fixtures = path.resolve(__dirname, "../../backend/tests/fixtures/documents");

async function api(token, route, method = "GET", body) {
  const response = await fetch(`${BACKEND}${route}`, {method, headers: {authorization: `Bearer ${token}`, "content-type":"application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) throw new Error(`${method} ${route}: ${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
}
async function start(browser) {
  const response = await fetch(`${BACKEND}/api/auth/login`, {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({email:process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com", password:process.env.SELFHOST_ADMIN_PASSWORD})});
  expect(response.ok).toBe(true); const login=await response.json();
  await provisionAdminTenant(BACKEND, login);
  const context=await browser.newContext();
  await context.addInitScript(({login})=>window.sessionStorage.setItem("aitana:local_jwt_session",JSON.stringify({token:login.access_token,expiresAt:Date.now()+login.expires_in*1000,user:login.user})),{login});
  const page=await context.newPage(); page.setDefaultTimeout(30_000);
  return {context,page,token:login.access_token};
}
async function saveComplete(page, token, session, expected) {
  await expect.poll(async()=> (await api(token,`/api/sessions/${session}/documents`)).documents.map(({filename,included})=>({filename,included})).sort((a,b)=>a.filename.localeCompare(b.filename))).toEqual([...expected].sort((a,b)=>a.filename.localeCompare(b.filename)));
  await expect(page.locator("textarea").first()).toBeEnabled();
}

test("普通新对话上传、格式解析、取消选择、刷新与会话切换", async ({browser}, info)=>{
  const {context,page,token}=await start(browser); const created=[];
  page.on("response",async response=>{if(response.url().endsWith("/api/documents/upload") && response.ok()) {const row=await response.json();created.push(row.docId);}});
  try {
    await page.goto(`${FRONTEND}/chat/root-agent`);
    const picker=page.getByLabel("上传对话附件");
    await expect(page.getByRole("button",{name:"添加文件或拖入此处"})).toBeEnabled();
    await picker.setInputFiles([
      {name:"budget.txt",mimeType:"text/plain",buffer:Buffer.from("批次 ALPHA119\n原值 1000；现值 620")},
      ...["sample.pdf","sample.docx","sample.xlsx","sample.pptx"].map(name=>path.join(fixtures,name)),
    ]);
    await expect(page.getByText("可用于分析",{exact:true})).toHaveCount(5);
    await expect(page).toHaveURL(/session=/);
    const first=new URL(page.url()).searchParams.get("session");
    const names=["budget.txt","sample.pdf","sample.docx","sample.xlsx","sample.pptx"];
    await saveComplete(page,token,first,names.map(filename=>({filename,included:true})));
    for (const id of created) expect((await api(token,`/api/documents/${id}`)).blocks.length).toBeGreaterThan(0);
    await page.getByRole("checkbox",{name:"取消分析 sample.xlsx",exact:true}).click();
    const restored=names.map(filename=>({filename,included:filename!=="sample.xlsx"}));
    await saveComplete(page,token,first,restored);
    await page.reload(); await saveComplete(page,token,first,restored);
    await expect(page.getByRole("checkbox",{name:"参与分析 sample.xlsx",exact:true})).toHaveAttribute("aria-checked","false");
    await page.getByRole("button",{name:"移除 sample.pdf",exact:true}).click();
    await saveComplete(page,token,first,restored.filter(row=>row.filename!=="sample.pdf"));
    // A distinct existing session must start with an empty attachment list.
    const second=`files-${randomUUID()}`;
    await api(token,`/api/sessions/${second}/bootstrap`,"POST",{skill_id:"root-agent",agent_id:"root-agent"});
    await page.goto(`${FRONTEND}/chat/root-agent?session=${second}`);
    await expect(page.locator("textarea").first()).toBeEnabled();
    await expect(page.getByRole("checkbox",{name:/分析 budget.txt/})).toHaveCount(0);
    await picker.setInputFiles({name:"broken.pdf",mimeType:"application/pdf",buffer:Buffer.from("not a PDF")});
    await expect(page.getByText("处理失败",{exact:true})).toBeVisible();
    await expect(page.locator("textarea").first()).toBeDisabled();
    expect((await api(token,`/api/sessions/${second}/documents`)).documents[0].parseStatus).toBe("failed");
    await page.screenshot({path:info.outputPath("chat-file-failure.png"),fullPage:true});
    await page.goto(`${FRONTEND}/chat/root-agent?session=${first}`);
    await saveComplete(page,token,first,restored.filter(row=>row.filename!=="sample.pdf"));
    await page.screenshot({path:info.outputPath("chat-file-restored.png"),fullPage:true});
  } finally {
    await context.close();
    for (const id of created) await api(token,`/api/documents/${id}`,"DELETE");
  }
});

test("真实 Provider 从新对话附件中读取未知编号、计算差额并引用来源",async({browser},info)=>{
  test.skip(!REAL,"需要真实 Provider URL、模型和后端 OPENAI_API_KEY；普通浏览器验收不证明模型分析。");
  test.setTimeout(180_000);
  const {context,page,token}=await start(browser); const suffix=randomUUID().slice(0,8);
  const provider=`file-provider-${suffix}`, model=`file-model-${suffix}`, marker=`BATCH-${randomUUID()}`;
  const original=await api(token,"/api/admin/platform-config"); const ids=[];
  let providerCreated=false,modelCreated=false,rootTouched=false;
  try {
    await api(token,`/api/admin/model-providers/${provider}`,"PUT",{name:"附件真实模型验收",kind:"openai-compatible",base_url:process.env.REAL_PROVIDER_BASE_URL,api_key_ref:"${OPENAI_API_KEY}",enabled:true}); providerCreated=true;
    await api(token,`/api/admin/model-providers/models/${model}`,"PUT",{api_name:process.env.REAL_PROVIDER_MODEL,provider_id:provider,tier:"default",context_window:32_000,max_output_tokens:2048,supports_tools:true,supports_reasoning:false,supports_responses_api:false,supports_vision:false,residency:"global",enabled:true}); modelCreated=true;
    await api(token,"/api/admin/platform-config","PUT",{agent:{...original.agent,model,skills:[],tools:[],mcpServers:[],instructions:"根据本轮附件回答，给出计算依据和文件名、行号。没有读取到内容时明确说明，不得猜测。"}}); rootTouched=true;
    await page.goto(`${FRONTEND}/chat/root-agent`);
    await expect(page.getByRole("button",{name:"添加文件或拖入此处"})).toBeEnabled();
    const uploads=[];
    page.on("response",async response=>{if(response.url().endsWith("/api/documents/upload")&&response.ok()) {const row=await response.json(); ids.push(row.docId); uploads.push(row);}});
    await page.getByLabel("上传对话附件").setInputFiles([
      {name:"批次.txt",mimeType:"text/plain",buffer:Buffer.from(`批次编号：${marker}`)},
      {name:"数值.csv",mimeType:"text/csv",buffer:Buffer.from("项目,原值,现值\n费用,1297,817\n")},
    ]);
    await expect(page.getByText("可用于分析",{exact:true})).toHaveCount(2);
    const composer=page.locator("textarea").first(); await expect(composer).toBeEnabled();
    const stream=page.waitForResponse(r=>r.url().endsWith("/api/agent/stream")&&r.request().method()==="POST");
    await composer.fill("请给出附件中的批次编号，计算费用从原值到现值减少了多少，并注明两个文件名及对应行号。"); await composer.press("Enter");
    const response=await stream; expect(response.ok()).toBe(true);
    const wire=await response.text(); const events=wire.split("\n").filter(line=>line.startsWith("data:")).map(line=>JSON.parse(line.slice(5)));
    expect(events.some(event=>event.type==="RUN_ERROR")).toBe(false);
    expect(events.some(event=>event.type==="RUN_FINISHED")).toBe(true);
    const text=events.filter(event=>event.type==="TEXT_MESSAGE_CONTENT").map(event=>event.delta).join("");
    expect(text).toContain(marker); expect(text).toMatch(/480/); expect(text).toContain("批次.txt"); expect(text).toContain("数值.csv"); expect(text).toMatch(/行/);
    const sent=JSON.parse(response.request().postData()); expect(sent.forwardedProps.document_ids.sort()).toEqual(ids.sort());
    await expect(page.getByText(marker,{exact:false}).first()).toBeVisible();
    await page.screenshot({path:info.outputPath("chat-file-real-provider.png"),fullPage:true});
    await info.attach("analysis-evidence",{body:JSON.stringify({providerBase:process.env.REAL_PROVIDER_BASE_URL,model:process.env.REAL_PROVIDER_MODEL,uploads,answer:text},null,2),contentType:"application/json"});
  } finally {
    await context.close();
    if(rootTouched) await api(token,"/api/admin/platform-config","PUT",{agent:original.agent});
    if(modelCreated) await api(token,`/api/admin/model-providers/models/${model}`,"DELETE");
    if(providerCreated) await api(token,`/api/admin/model-providers/${provider}`,"DELETE");
    for(const id of ids) await api(token,`/api/documents/${id}`,"DELETE");
  }
});
