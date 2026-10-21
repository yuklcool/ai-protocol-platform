import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let auth = { user: { uid: "u1" } as { uid: string } | null, loading: false };
let locale = "zh-CN";
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale }) }));
vi.mock("@/components/chat/SignInRequired", () => ({ SignInRequired: () => <p>请登录</p> }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));

import SkillsPage from "@/app/skills/page";
import { useUserSkills } from "@/hooks/useUserSkills";
import { fetchWithAuth } from "@/lib/apiClient";

const fetchMock = vi.mocked(fetchWithAuth);
const PROFILE = "/api/proxy/api/auth/profile";
const AGENT = "/api/proxy/api/agent";
const LIST = "/api/proxy/api/skills";
const own = { skillId: "own", name: "own", displayName: "我的研究", description: "研究分析", ownerId: "u1", skillMetadata: {}, accessControl: { type: "private" } };
const shared = { ...own, skillId: "shared", displayName: "共享分析", ownerId: "u2", accessControl: { type: "tagged" } };
const platform = { ...own, skillId: "platform", displayName: "平台写作", ownerId: "aitana-platform", accessControl: { type: "public" } };
const publicSkill = { ...shared, skillId: "public", displayName: "公共能力", accessControl: { type: "public" } };
let skills = [own, shared, platform, publicSkill];
let profile = { skills: [] as string[], information: "保留个人信息" };
let access: Record<string, number>;
let agentBody: unknown;
let listStatus: number;
let profileStatus: number;
let putStatus: number;
let putBody: unknown;
let writes: typeof profile[];

function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
async function ready() {
  await screen.findByRole("article", { name: "我的研究" });
  await waitFor(() => expect(screen.queryByText(/正在确认可用性/)).not.toBeInTheDocument());
}
function card(name = "我的研究") { return within(screen.getByRole("article", { name })); }

beforeEach(() => {
  auth = { user: { uid: "u1" }, loading: false };
  locale = "zh-CN";
  skills = [own, shared, platform, publicSkill];
  profile = { skills: [], information: "保留个人信息" };
  access = { own: 404, shared: 404, platform: 404, public: 404 };
  agentBody = { skillId: "root-agent", skillMetadata: {} };
  listStatus = profileStatus = putStatus = 200;
  putBody = undefined;
  writes = [];
  vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", "false");
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (input, options) => {
    const path = String(input);
    if (path === LIST) return response(skills, listStatus);
    if (path === PROFILE && options?.method === "PUT") {
      const body = JSON.parse(String(options.body));
      writes.push(body);
      if (putStatus === 200) {
        profile = body;
        for (const id of body.skills) access[id] = 200;
      }
      return response(putBody ?? body, putStatus);
    }
    if (path === PROFILE) return response(profile, profileStatus);
    if (path === AGENT) return response(agentBody);
    const id = decodeURIComponent(path.slice(`${AGENT}/capabilities/`.length));
    return response({ skillId: id, skillMetadata: {} }, access[id] ?? 503);
  });
});
afterEach(() => { vi.unstubAllEnvs(); });

describe("能力中心", () => {
  it("保留 ACL 共享候选，仅 owner 可以编辑与个人启用，不将 visible 当作可调用", async () => {
    render(<SkillsPage />);
    await ready();
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(card().queryByRole("link", { name: "编辑" })).not.toBeInTheDocument();
    expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled();
    for (const name of ["共享分析", "平台写作", "公共能力"]) {
      expect(card(name).queryByRole("link", { name: "编辑" })).not.toBeInTheDocument();
      expect(card(name).queryByRole("button", { name: "为我启用" })).not.toBeInTheDocument();
      expect(card(name).getByRole("button", { name: "开始使用" })).toBeDisabled();
      expect(card(name).getByText(/请管理员检查/)).toBeInTheDocument();
    }
    expect(writes).toEqual([]);
  });

  it.each(["domain", "specific", "tagged"])("保留后端返回的 %s 共享候选，不开放编辑与个人启用", async (type) => {
    skills = [{ ...shared, accessControl: { type } }];
    render(<SkillsPage />);
    await screen.findByRole("article", { name: "共享分析" });
    await waitFor(() => expect(screen.queryByText(/正在确认可用性/)).not.toBeInTheDocument());
    expect(card("共享分析").getByRole("button", { name: "开始使用" })).toBeDisabled();
    expect(card("共享分析").queryByRole("button", { name: "为我启用" })).not.toBeInTheDocument();
    expect(card("共享分析").queryByRole("link", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("个人启用重新 GET 并合并完整 profile，保留其他绑定与最新 information", async () => {
    render(<SkillsPage />);
    await ready();
    await waitFor(() => expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled());
    profile = { skills: ["another", "another"], information: "另一页面刚刚更新的信息\n不可丢失" };
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await waitFor(() => expect(card().getByText("已为我启用")).toBeInTheDocument());
    expect(writes).toEqual([{ skills: ["another", "own"], information: "另一页面刚刚更新的信息\n不可丢失" }]);
    const request = fetchMock.mock.calls.find(([, options]) => options?.method === "PUT");
    expect(request?.[1]?.headers).toEqual({ "Content-Type": "application/json" });
    expect(card().queryByRole("button", { name: "为我启用" })).not.toBeInTheDocument();
    expect(await card().findByRole("link", { name: "开始使用" })).toHaveAttribute("href", "/chat/own");
  });

  it.each([422, 500])("PUT %s 失败不冒成功，可重新启用", async (status) => {
    putStatus = status;
    render(<SkillsPage />);
    await ready();
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await screen.findByText(/启用失败/);
    expect(card().queryByText("已为我启用")).not.toBeInTheDocument();
    expect(card().getByRole("button", { name: "开始使用" })).toBeDisabled();
    expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled();
    expect(writes[0].information).toBe("保留个人信息");
    putStatus = 200;
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await card().findByText("已为我启用");
    expect(screen.queryByText(/启用失败/)).not.toBeInTheDocument();
  });

  it("初始绑定检查迟到不能覆盖启用后的新确认", async () => {
    const lateCheck = deferred<Response>();
    const router = fetchMock.getMockImplementation()!;
    let firstCheck = true;
    fetchMock.mockImplementation((input, options) => {
      if (String(input) === `${AGENT}/capabilities/own` && firstCheck) {
        firstCheck = false;
        return lateCheck.promise;
      }
      return router(input, options);
    });
    render(<SkillsPage />);
    await screen.findByRole("article", { name: "我的研究" });
    await waitFor(() => expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled());
    await waitFor(() => expect(firstCheck).toBe(false));
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await card().findByRole("link", { name: "开始使用" });
    await act(async () => { lateCheck.resolve(response({}, 404)); });
    expect(card().getByRole("link", { name: "开始使用" })).toHaveAttribute("href", "/chat/own");
  });

  it("保存成功但运行时仍未知，只展示已启用而不放开开始", async () => {
    const router = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, options) => String(input) === `${AGENT}/capabilities/own`
      ? Promise.resolve(response({}, 503)) : router(input, options));
    render(<SkillsPage />);
    await ready();
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await card().findByText("已为我启用");
    expect(card().getByRole("button", { name: "开始使用" })).toBeDisabled();
    expect(card().getByText("可用状态未知")).toBeInTheDocument();
  });

  it("PUT 响应未确认目标绑定时不显示成功", async () => {
    putBody = { skills: [], information: "保留个人信息" };
    render(<SkillsPage />);
    await ready();
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await screen.findByText(/启用失败/);
    expect(card().queryByText("已为我启用")).not.toBeInTheDocument();
  });

  it("点击时 profile 读取失败或缺失 information，绝不 PUT 部分资料", async () => {
    render(<SkillsPage />);
    await ready();
    profileStatus = 503;
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await screen.findByText(/启用失败/);
    expect(writes).toEqual([]);
    profileStatus = 200;
    profile = { skills: [] } as unknown as typeof profile;
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await waitFor(() => expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled());
    expect(writes).toEqual([]);
  });

  it("当前 profile 决定个人启用标记，但不越过服务端未知状态启用开始", async () => {
    profile.skills = ["own", "shared"];
    access.own = 503;
    render(<SkillsPage />);
    await ready();
    expect(card().getByText("已为我启用")).toBeInTheDocument();
    expect(card().getByText("可用状态未知")).toBeInTheDocument();
    expect(card().getByRole("button", { name: "开始使用" })).toBeDisabled();
    expect(card("共享分析").queryByText("已为我启用")).not.toBeInTheDocument();
    expect(card().queryByRole("button", { name: "为我启用" })).not.toBeInTheDocument();
  });

  it("公共/共享能力仅在服务端确认后可开始，不修改 profile 或自动发消息", async () => {
    access.public = access.shared = 200;
    render(<SkillsPage />);
    await ready();
    expect(card("公共能力").getByRole("link", { name: "开始使用" })).toHaveAttribute("href", "/chat/public");
    expect(card("共享分析").getByRole("link", { name: "开始使用" })).toHaveAttribute("href", "/chat/shared");
    expect(card("公共能力").queryByText("已为我启用")).not.toBeInTheDocument();
    expect(writes).toEqual([]);
    expect(fetchMock.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
  });

  it("/agent 返回实际 SkillResponse 以外的猜测绑定 shape 时保持未知", async () => {
    agentBody = { skills: ["public"] };
    access.public = 200;
    render(<SkillsPage />);
    await ready();
    expect(card("公共能力").getByRole("button", { name: "开始使用" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/capabilities/"))).toBe(false);
    agentBody = { skillId: "root-agent", skillMetadata: {} };
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await ready();
    await card("公共能力").findByRole("link", { name: "开始使用" });
  });

  it("profile 加载失败不提供启用按钮，已确认的公共绑定仍能使用", async () => {
    profileStatus = 503;
    access.public = 200;
    render(<SkillsPage />);
    await ready();
    expect(screen.getByText(/个人启用状态未知/)).toBeInTheDocument();
    expect(card().queryByRole("button", { name: "为我启用" })).not.toBeInTheDocument();
    expect(card("公共能力").getByRole("link", { name: "开始使用" })).toBeInTheDocument();
  });

  it.each(["false", "true"])("创建开关 %s 同时控制头部、空态新建与平台 Studio fork", async (enabled) => {
    vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", enabled);
    const { rerender } = render(<SkillsPage />);
    await ready();
    const expected = enabled === "true";
    expect(!!card().queryByRole("link", { name: "编辑" })).toBe(expected);
    if (expected) expect(card().getByRole("link", { name: "编辑" })).toHaveAttribute("href", "/skills/studio/own");
    expect(!!screen.queryByRole("link", { name: "新建技能" })).toBe(expected);
    expect(!!card("平台写作").queryByRole("link", { name: "在 Studio 中创建副本" })).toBe(expected);
    if (expected) expect(card("平台写作").getByRole("link", { name: "在 Studio 中创建副本" })).toHaveAttribute("href", "/skills/studio/platform");
    skills = [];
    auth.user = { uid: "u3" };
    rerender(<SkillsPage />);
    await screen.findByText("暂无可见能力");
    expect(screen.queryAllByRole("link", { name: "新建技能" })).toHaveLength(expected ? 2 : 0);
  });

  it("支持我的技能筛选、搜索与清除", async () => {
    render(<SkillsPage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "我的技能" }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "无匹配" } });
    expect(screen.getByText("没有匹配的技能")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清除搜索" }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "发现能力" }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "研究分析" } });
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("英文页面与未知状态", async () => {
    vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", "true");
    locale = "en";
    access.own = 503;
    render(<SkillsPage />);
    await screen.findByText("Capability center");
    await waitFor(() => expect(card().getByRole("button", { name: "Enable for me" })).toBeEnabled());
    expect(card().getByRole("button", { name: "Start using" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "My skills" })).toBeInTheDocument();
    expect(card().getByRole("link", { name: "Edit" })).toBeInTheDocument();
  });

  it("列表失败提供重试并恢复，空列表保留空态", async () => {
    listStatus = 503;
    render(<SkillsPage />);
    await screen.findByText("技能加载失败。");
    listStatus = 200;
    skills = [];
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("暂无可见能力");
  });

  it("认证加载/未登录不请求数据", () => {
    auth.loading = true;
    const { rerender } = render(<SkillsPage />);
    expect(screen.queryByRole("heading", { name: "能力中心" })).not.toBeInTheDocument();
    auth.loading = false;
    auth.user = null;
    rerender(<SkillsPage />);
    expect(screen.getByText("请登录")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("账号 key 隔离搜索、profile 与迟到的 Agent 响应", async () => {
    const lateAgent = deferred<Response>();
    const router = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, options) => String(input) === AGENT ? lateAgent.promise : router(input, options));
    const { rerender } = render(<SkillsPage />);
    await screen.findByRole("article", { name: "我的研究" });
    await waitFor(() => expect(card().getByRole("button", { name: "为我启用" })).toBeEnabled());
    const oldSignal = fetchMock.mock.calls.find(([path]) => path === AGENT)?.[1]?.signal;
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "研究" } });
    fetchMock.mockImplementation(router);
    auth.user = { uid: "u2" };
    profile = { skills: ["shared"], information: "u2 的资料" };
    rerender(<SkillsPage />);
    expect(screen.getByRole("searchbox")).toHaveValue("");
    await ready();
    expect(oldSignal?.aborted).toBe(true);
    expect(card("共享分析").getByText("已为我启用")).toBeInTheDocument();
    expect(card().queryByRole("link", { name: "编辑" })).not.toBeInTheDocument();
    access.own = 200;
    await act(async () => { lateAgent.resolve(response({ skillId: "root-agent", skillMetadata: {} })); });
    expect(card().getByRole("button", { name: "开始使用" })).toBeDisabled();
  });

  it("启用过程账号切换后，旧 profile PUT 迟到不能污染新账号", async () => {
    const pending = deferred<Response>();
    const router = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, options) => options?.method === "PUT" ? pending.promise : router(input, options));
    const { rerender } = render(<SkillsPage />);
    await ready();
    fireEvent.click(card().getByRole("button", { name: "为我启用" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(true));
    auth.user = { uid: "u2" };
    rerender(<SkillsPage />);
    await ready();
    await act(async () => { pending.resolve(response({ skills: ["own"], information: "旧账号" })); });
    expect(card("共享分析").queryByText("已为我启用")).not.toBeInTheDocument();
    expect(card("共享分析").getByRole("button", { name: "为我启用" })).toBeEnabled();
    expect(card().getByRole("button", { name: "开始使用" })).toBeDisabled();
  });
});

describe("能力列表异步隔离", () => {
  it("uid 变化/退出立即清空，忽略不遵守 abort 的旧请求及 finally", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    fetchMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(({ uid }) => useUserSkills(uid), { initialProps: { uid: "u1" as string | null } });
    rerender({ uid: "u2" });
    expect(result.current.skills).toEqual([]);
    await act(async () => { first.resolve(response([own])); });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.skills).toEqual([]);
    await act(async () => { second.resolve(response([shared])); });
    expect(result.current.skills.map((skill) => skill.skillId)).toEqual(["shared"]);
    rerender({ uid: null });
    expect(result.current.skills).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it("旧请求迟到失败不覆盖当前用户成功结果", async () => {
    const first = deferred<Response>();
    fetchMock.mockReturnValueOnce(first.promise).mockResolvedValueOnce(response([shared]));
    const { result, rerender } = renderHook(({ uid }) => useUserSkills(uid), { initialProps: { uid: "u1" } });
    rerender({ uid: "u2" });
    await waitFor(() => expect(result.current.skills).toHaveLength(1));
    await act(async () => { first.resolve(response({}, 500)); });
    expect(result.current.error).toBeNull();
    expect(result.current.skills[0].skillId).toBe("shared");
  });
});
