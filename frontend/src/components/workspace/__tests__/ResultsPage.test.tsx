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
const row = (session_id: string, title = session_id) => ({ session_id, title, skill_id: "actual/skill", owner_uid: "u1" });
const results = (session_id: string, extra = {}) => ({ session_id, state_available: true, incomplete_count: 0, truncated: false, results: [{ surface_id: "workspace", title: "Saved result", description: "Actual metadata", kind: "report", created_at: 1 }], ...extra });

beforeEach(() => {
  auth.user = { uid: "u1" }; auth.loading = false; auth.locale = "en";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async url => String(url).endsWith("/reports") ? response({ reports: [] }) : String(url).endsWith("/results") ? response(results("s1")) : response({ sessions: [row("s1", "Task one")], next_cursor: null }));
});

describe("ResultsPage", () => {
  it("requires authentication before loading private results", async () => {
    auth.user = null;
    const { rerender } = render(<ResultsPage />);
    expect(screen.getByText("Sign in required")).toBeInTheDocument(); expect(fetchMock).not.toHaveBeenCalled();
    auth.user = { uid: "u1" }; rerender(<ResultsPage />);
    expect(await screen.findByText("Saved result")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to conversation" })).toHaveAttribute("href", "/chat/actual%2Fskill?session=s1");
  });
  it("shows reports and surface summaries without requiring session selection", async () => {
    fetchMock.mockImplementation(async url => String(url).endsWith("/reports") ? response({ reports: [{ report_id: "r", message_id: "m", title: "Quarterly report", content: "Saved report body", revision: 2, updated_at: "2026-10-23T00:00:00Z" }] }) : String(url).endsWith("/results") ? response(results("s1")) : response({ sessions: [row("s1", "Task one")], next_cursor: null }));
    render(<ResultsPage />);
    expect(await screen.findByText("Quarterly report")).toBeInTheDocument(); expect(screen.getByText("Saved result")).toBeInTheDocument();
    expect(screen.getByText("Saved report body")).toBeInTheDocument();
  });
  it("searches all session metadata on submit", async () => {
    render(<ResultsPage />); await screen.findByText("Saved result");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "older & task" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/proxy/api/sessions/search?q=older%20%26%20task", expect.anything()));
  });
  it("does not treat unavailable or incomplete state as an empty result", async () => {
    fetchMock.mockImplementation(async url => String(url).endsWith("/reports") ? response({ reports: [] }) : String(url).endsWith("/results") ? response(results("s1", { state_available: false, incomplete_count: 2, truncated: true, results: [] })) : response({ sessions: [row("s1")], next_cursor: null }));
    render(<ResultsPage />);
    expect(await screen.findByText(/Result state is unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/2 state entries are incomplete/)).toBeInTheDocument();
    expect(screen.getByText(/Only the first 100 results/)).toBeInTheDocument();
    expect(screen.queryByText(/No persisted interactive-result summaries/)).not.toBeInTheDocument();
  });
  it("isolates late responses after account switching", async () => {
    let finish!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { rerender } = render(<ResultsPage />);
    fetchMock.mockResolvedValue(response({ sessions: [], next_cursor: null }));
    auth.user = { uid: "u2" }; rerender(<ResultsPage />);
    await act(async () => finish(response({ sessions: [row("secret", "Foreign secret")], next_cursor: null })));
    expect(screen.queryByText("Foreign secret")).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("");
  });
  it("shows permission errors without pretending there are no results", async () => {
    fetchMock.mockImplementation(async url => String(url).endsWith("/results") ? response({}, 403) : response({ sessions: [row("s1")], next_cursor: null }));
    render(<ResultsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot access these results");
    expect(screen.queryByText(/No persisted interactive-result summaries/)).not.toBeInTheDocument();
  });
  it("removes confirmed empty sources and keeps earlier-page navigation", async () => {
    fetchMock.mockImplementation(async url => String(url).endsWith("/reports") ? response({ reports: [] }) : String(url).endsWith("/results") ? response(results("s1", { results: [] })) : response({ sessions: [row("s1", "Empty conversation")], next_cursor: "earlier" }));
    render(<ResultsPage />);
    expect(await screen.findByText("No saved results in the checked conversations")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Empty conversation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load more results" })).toBeEnabled();
  });
  it("keeps transcript-loss warnings even when the saved result list is empty", async () => {
    fetchMock.mockImplementation(async url => String(url).endsWith("/reports") ? response({ reports: [] }) : String(url).endsWith("/results") ? response(results("s1", { results: [] })) : response({ sessions: [{ ...row("s1"), transcript_lost: true }], next_cursor: null }));
    render(<ResultsPage />);
    fireEvent.click(await screen.findByText("Result state needs review"));
    expect(await screen.findByText(/transcript may be unavailable/)).toBeVisible();
    await waitFor(() => expect(screen.queryByText(/Loading results/)).not.toBeInTheDocument());
    expect(screen.queryByText("No saved results in the checked conversations")).not.toBeInTheDocument();
  });
});
