import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ user: null as { uid: string } | null, loading: false, locale: "en" }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: auth.locale }) }));
vi.mock("@/components/chat/SignInRequired", () => ({ SignInRequired: () => <div>Sign in required</div> }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
import { fetchWithAuth } from "@/lib/apiClient";
import ResultsPage from "@/app/results/page";
const fetchMock = vi.mocked(fetchWithAuth);
const response = (body: unknown, status = 200) => ({ ok: status === 200, status, json: async () => body }) as Response;
const row = (session_id: string, title = session_id) => ({ session_id, title, skill_id: "actual/skill", owner_uid: "not-skill-owner", skill_label: "Research" });
const results = (session_id: string, extra = {}) => ({ session_id, state_available: true, incomplete_count: 0, truncated: false, results: [{ surface_id: "workspace", title: "Saved result", description: "Actual metadata", kind: "report", created_at: 1 }], ...extra });

beforeEach(() => {
  auth.user = { uid: "u1" };
  auth.loading = false;
  auth.locale = "en";
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(response({ sessions: [row("s1", "Task one"), row("s2", "Task two")], next_cursor: null }));
});

async function selectFirst() {
  fireEvent.click(await screen.findByRole("button", { name: "View results: Task one" }));
}

describe("ResultsPage", () => {
  it("does not request private data until authenticated", async () => {
    auth.loading = true;
    const { rerender } = render(<ResultsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking sign-in");
    expect(fetchMock).not.toHaveBeenCalled();
    auth.loading = false;
    auth.user = null;
    rerender(<ResultsPage />);
    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    auth.user = { uid: "u1" };
    rerender(<ResultsPage />);
    await screen.findByText("Task one");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("loads only the selected session metadata and links to its real skill without messages scans", async () => {
    render(<ResultsPage />);
    await screen.findByText("Task one");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(response(results("s1")));
    await selectFirst();
    expect(await screen.findByText("Saved result")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/proxy/api/sessions", "/api/proxy/api/sessions/s1/results"]);
    expect(screen.getByRole("link", { name: "Return to conversation" })).toHaveAttribute("href", "/chat/actual%2Fskill?session=s1");
    expect(screen.getByRole("time")).toHaveAttribute("datetime", "1970-01-01T00:00:00.001Z");
    expect(screen.getByRole("button", { name: "View results: Task one" })).toHaveAttribute("aria-pressed", "true");
  });

  it.each([403, 404, 500])("shows HTTP %s as error, not empty, and retries", async (status) => {
    render(<ResultsPage />);
    fetchMock.mockResolvedValueOnce(response({}, status));
    await selectFirst();
    await screen.findByRole("alert");
    expect(screen.queryByText(/No persisted interactive-result summaries were found/)).not.toBeInTheDocument();
    fetchMock.mockResolvedValueOnce(response(results("s1", { results: [] })));
    fireEvent.click(screen.getByRole("button", { name: "Retry results" }));
    expect(await screen.findByText(/No persisted interactive-result summaries were found/)).toBeInTheDocument();
  });

  it("rejects a mismatched session response instead of presenting it", async () => {
    render(<ResultsPage />);
    fetchMock.mockResolvedValueOnce(response(results("foreign")));
    await selectFirst();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load results");
    expect(screen.queryByText("Saved result")).not.toBeInTheDocument();
  });

  it("distinguishes unavailable, incomplete and truncated state from a complete empty result", async () => {
    render(<ResultsPage />);
    fetchMock.mockResolvedValueOnce(response(results("s1", { state_available: false, results: [], incomplete_count: 2, truncated: true })));
    await selectFirst();
    expect(await screen.findByText(/Result state is unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/2 state entries are incomplete/)).toBeInTheDocument();
    expect(screen.getByText(/Only the first 100 results/)).toBeInTheDocument();
    expect(screen.queryByText(/No persisted interactive-result summaries were found/)).not.toBeInTheDocument();
  });

  it("ignores a stale selected-session request even when transport ignores abort", async () => {
    render(<ResultsPage />);
    let resolveOld!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    await selectFirst();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const signal = fetchMock.mock.calls[1][1]?.signal;
    fetchMock.mockResolvedValueOnce(response(results("s2", { results: [] })));
    fireEvent.click(screen.getByRole("button", { name: "View results: Task two" }));
    await screen.findByText(/No persisted interactive-result summaries were found/);
    expect(signal?.aborted).toBe(true);
    await act(async () => resolveOld(response(results("s1"))));
    expect(screen.queryByText("Saved result")).not.toBeInTheDocument();
  });

  it("clears selected results and search on account switch", async () => {
    const { rerender } = render(<ResultsPage />);
    fetchMock.mockResolvedValueOnce(response(results("s1")));
    await selectFirst();
    await screen.findByText("Saved result");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "task" } });
    fetchMock.mockResolvedValueOnce(response({ sessions: [], next_cursor: null }));
    auth.user = { uid: "u2" };
    rerender(<ResultsPage />);
    expect(screen.queryByText("Saved result")).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("");
    await screen.findByText(/No sessions yet/);
  });

  it("paginates source sessions without requesting their results and searches only loaded rows", async () => {
    fetchMock.mockResolvedValueOnce(response({ sessions: [row("s1", "Task one")], next_cursor: "next &" }));
    render(<ResultsPage />);
    await screen.findByText("Task one");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "later" } });
    expect(screen.getByText("No matches in loaded sessions.")).toBeInTheDocument();
    fetchMock.mockResolvedValueOnce(response({ sessions: [row("later", "Later task")], next_cursor: null }));
    fireEvent.click(screen.getByRole("button", { name: "Load more sessions" }));
    expect(await screen.findByText("Later task")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/proxy/api/sessions?cursor=next%20%26");
    expect(fetchMock.mock.calls).toHaveLength(2);
  });

  it("shows session load errors with retry and Chinese scope text", async () => {
    auth.locale = "zh-CN";
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    render(<ResultsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("无法加载会话");
    expect(screen.getByRole("heading", { name: "我的成果" })).toBeInTheDocument();
    expect(screen.getByText(/不把上传附件当成成果/)).toBeInTheDocument();
    fetchMock.mockResolvedValueOnce(response({ sessions: [row("s ?&", "真实任务")], next_cursor: null }));
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("真实任务");
    fetchMock.mockResolvedValueOnce(response(results("s ?&")));
    fireEvent.click(screen.getByRole("button", { name: "查看成果：真实任务" }));
    await screen.findByText("Saved result");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/proxy/api/sessions/s%20%3F%26/results");
  });
});
