import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ user: null as { uid: string } | null, loading: false, locale: "en" }));
const route = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => route }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => state }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: state.locale }) }));
vi.mock("@/components/chat/SignInRequired", () => ({ SignInRequired: () => <div data-testid="sign-in-required">Sign in required</div> }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));

import { fetchWithAuth } from "@/lib/apiClient";
import WorkspacePage from "@/app/workspace/page";
import { consumeWorkspaceDraft } from "@/lib/workspaceDraft";
import SessionsPage from "@/app/sessions/page";
const fetchMock = vi.mocked(fetchWithAuth);

function row(id: string, title = id) {
  return { session_id: id, skill_id: "actual/agent", owner_uid: "not-the-skill-owner", title, skill_label: "Research", last_message_at: "2026-10-20T12:00:00Z", transcript_lost: false };
}
function ok(sessions: ReturnType<typeof row>[], next_cursor: string | null = null) {
  return { ok: true, json: async () => ({ sessions, next_cursor }) } as Response;
}

beforeEach(() => {
  state.user = null;
  state.loading = false;
  state.locale = "en";
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(ok([]));
  route.push.mockReset();
  window.sessionStorage.clear();
});

describe.each([["workspace", WorkspacePage], ["sessions", SessionsPage]] as const)("%s 登录边界", (_, Page) => {
  it("未登录原地显示 SignInRequired，不加载私人会话", () => {
    render(<Page />);
    expect(screen.getByTestId("sign-in-required")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("认证加载期间不加载会话，登录后在当前页恢复", async () => {
    state.loading = true;
    const { rerender } = render(<Page />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking sign-in");
    expect(fetchMock).not.toHaveBeenCalled();
    state.loading = false;
    rerender(<Page />);
    expect(screen.getByTestId("sign-in-required")).toBeInTheDocument();
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1", "Private task")]));
    rerender(<Page />);
    expect(await screen.findByText("Private task")).toBeInTheDocument();
    expect(screen.queryByTestId("sign-in-required")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/proxy/api/sessions");
  });

  it("uid 切换重建 child，旧请求即使忽略取消也不能泄漏旧会话", async () => {
    state.user = { uid: "u1" };
    let resolveOld!: (response: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    fetchMock.mockResolvedValueOnce(ok([row("u2-session", "Second user")]));
    const { rerender } = render(<Page />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    state.user = { uid: "u2" };
    rerender(<Page />);
    expect(await screen.findByText("Second user")).toBeInTheDocument();
    await act(async () => resolveOld(ok([row("secret", "First user secret")])));
    expect(screen.queryByText("First user secret")).not.toBeInTheDocument();
    state.user = null;
    rerender(<Page />);
    expect(screen.getByTestId("sign-in-required")).toBeInTheDocument();
    expect(screen.queryByText("Second user")).not.toBeInTheDocument();
  });

  it("初始错误不误报空会话，重试可恢复且恢复链接安全", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    fetchMock.mockResolvedValueOnce(ok([row("s ?&", "Recovered task")]));
    render(<Page />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load sessions");
    expect(screen.queryByText(/No sessions yet/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: /Recovered task/ })).toHaveAttribute("href", "/chat/actual%2Fagent?session=s%20%3F%26");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("workspace 最近会话", () => {
  it("只显示真实最近卡片并提供 Root Agent 和全部会话入口", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("recent", "Actual task")]));
    render(<WorkspacePage />);
    expect(await screen.findByText("Actual task")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a task" })).toHaveAttribute("href", "/chat/root-agent");
    expect(screen.getByRole("link", { name: "All sessions" })).toHaveAttribute("href", "/sessions");
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find results" })).toHaveAttribute("href", "/results");
    expect(screen.getByRole("link", { name: "Discover capabilities" })).toHaveAttribute("href", "/skills");
  });

  it("zh 文案、真实空状态仍允许开始任务", async () => {
    state.user = { uid: "u1" };
    state.locale = "zh-CN";
    render(<WorkspacePage />);
    expect(await screen.findByText("还没有会话，开始一项任务吧。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "工作台" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始任务" })).toHaveAttribute("href", "/chat/root-agent");
  });
});

describe("workspace goal-first task entry", () => {
  it("prefills a fresh chat draft, does not send a message or create a session", async () => {
    state.user = { uid: "u1" };
    render(<WorkspacePage />);
    await screen.findByText("No sessions yet. Start a task to begin.");
    fireEvent.change(screen.getByRole("textbox", { name: "Task goal" }), {
      target: { value: "  Analyze the uploaded report  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /Continue in chat/ }));
    expect(route.push).toHaveBeenCalledWith("/chat/root-agent");
    expect(consumeWorkspaceDraft("u1")).toBe("Analyze the uploaded report");
    expect(consumeWorkspaceDraft("u1")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1); // the existing session list only
  });

  it("example goals populate the draft without sending or navigating", async () => {
    state.user = { uid: "u1" };
    render(<WorkspacePage />);
    await screen.findByText("No sessions yet. Start a task to begin.");
    fireEvent.click(screen.getByRole("button", { name: "Prepare a structured report" }));
    expect(screen.getByRole("textbox", { name: "Task goal" })).toHaveValue("Prepare a structured report");
    expect(route.push).not.toHaveBeenCalled();
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });
});

describe("sessions 全局列表", () => {
  it("搜索仅覆盖已加载会话，可翻页扩展结果并去重", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1", "First task")], "p2"));
    fetchMock.mockResolvedValueOnce(ok([row("s1", "First task"), row("s2", "Later task")]));
    render(<SessionsPage />);
    await screen.findByText("First task");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search loaded sessions" }), { target: { value: "later" } });
    expect(screen.getByText("No matches in loaded sessions.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Later task")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/proxy/api/sessions?cursor=p2");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("翻页错误保留已有卡片，不误空，可再次加载同一游标", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1", "Kept task")], "p2"));
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    fetchMock.mockResolvedValueOnce(ok([row("s2", "Next task")]));
    render(<SessionsPage />);
    await screen.findByText("Kept task");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByRole("alert");
    expect(screen.getByText("Kept task")).toBeInTheDocument();
    expect(screen.queryByText(/No sessions yet/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Next task")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/proxy/api/sessions?cursor=p2");
  });

  it("加载更多禁用按钮防止重复请求，uid 切换清空搜索", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1", "First task")], "p2"));
    let resolvePage!: (response: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolvePage = resolve; }));
    const { rerender } = render(<SessionsPage />);
    await screen.findByText("First task");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(screen.getByRole("button", { name: "Loading more…" })).toBeDisabled();
    await act(async () => resolvePage(ok([row("s2")])));
    state.user = { uid: "u2" };
    rerender(<SessionsPage />);
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.queryByText("First task")).not.toBeInTheDocument();
    await screen.findByText(/No sessions yet/);
  });

  it("zh 搜索、分页与返回工作台文案", async () => {
    state.user = { uid: "u1" };
    state.locale = "zh-CN";
    fetchMock.mockResolvedValueOnce(ok([row("s1")], "p2"));
    render(<SessionsPage />);
    expect(await screen.findByRole("button", { name: "加载更多" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "搜索已加载会话" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回工作台" })).toHaveAttribute("href", "/workspace");
  });
});
