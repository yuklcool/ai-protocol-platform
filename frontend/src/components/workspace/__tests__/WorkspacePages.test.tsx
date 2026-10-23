import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ user: null as { uid: string } | null, loading: false, locale: "en" }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => state }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: state.locale }) }));
vi.mock("@/components/chat/SignInRequired", () => ({ SignInRequired: () => <div data-testid="sign-in-required">Sign in required</div> }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));

import { fetchWithAuth } from "@/lib/apiClient";
import WorkspacePage from "@/app/workspace/page";
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
    expect(fetchMock.mock.calls[0][0]).toBe("/api/proxy/api/sessions/search");
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
    expect(screen.getByRole("link", { name: "New task" })).toHaveAttribute("href", "/chat/root-agent");
    expect(screen.getByRole("link", { name: "Search all sessions" })).toHaveAttribute("href", "/sessions");
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View results" })).toHaveAttribute("href", "/results");
    expect(screen.getByRole("link", { name: "Explore capabilities" })).toHaveAttribute("href", "/skills");
  });

  it("zh 文案、真实空状态仍允许开始任务", async () => {
    state.user = { uid: "u1" };
    state.locale = "zh-CN";
    render(<WorkspacePage />);
    expect(await screen.findByText("还没有会话，开始一项任务吧。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "任务概览" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始新任务" })).toHaveAttribute("href", "/chat/root-agent");
  });
});

describe("sessions 全局列表", () => {
  it("提交服务端搜索覆盖未加载历史，翻页保留查询并去重", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1", "First task")], "old-page"));
    fetchMock.mockResolvedValueOnce(ok([row("s2", "Later task")], "search-page"));
    fetchMock.mockResolvedValueOnce(ok([row("s2", "Later task"), row("s3", "Another later task")]));
    render(<SessionsPage />);
    await screen.findByText("First task");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search sessions" }), { target: { value: "later" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /^Search$/ }));
    expect(await screen.findByText("Later task")).toBeInTheDocument();
    expect(screen.queryByText("First task")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/proxy/api/sessions/search?q=later");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Another later task")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/proxy/api/sessions/search?q=later&cursor=search-page");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("日期条件按本地整天转换，错误范围不请求，空搜索可重置", async () => {
    state.user = { uid: "u1" };
    fetchMock.mockResolvedValueOnce(ok([row("s1")]));
    fetchMock.mockResolvedValueOnce(ok([]));
    fetchMock.mockResolvedValueOnce(ok([row("s2", "Reset result")]));
    render(<SessionsPage />);
    await screen.findByText("s1");
    fireEvent.change(screen.getByLabelText("Updated from"), { target: { value: "2026-10-22" } });
    fireEvent.change(screen.getByLabelText("Updated through"), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: /^Search$/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Start date must not follow end date.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Updated from"), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: /^Search$/ }));
    expect(await screen.findByText("No matching sessions. Try different filters.")).toBeInTheDocument();
    const start = encodeURIComponent(new Date("2026-10-20T00:00:00").toISOString());
    const end = encodeURIComponent(new Date("2026-10-21T00:00:00").toISOString());
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/proxy/api/sessions/search?updated_after=${start}&updated_before=${end}`);
    fireEvent.click(screen.getByRole("button", { name: /^Reset$/ }));
    expect(await screen.findByText("Reset result")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/proxy/api/sessions/search");
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
    expect(fetchMock.mock.calls[2][0]).toBe("/api/proxy/api/sessions/search?cursor=p2");
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
    expect(screen.getByRole("searchbox", { name: "搜索历史会话" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回工作台" })).toHaveAttribute("href", "/workspace");
  });
});
