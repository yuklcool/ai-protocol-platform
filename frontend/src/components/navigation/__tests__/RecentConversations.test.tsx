import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RecentConversations } from "../RecentConversations";
import { fetchWithAuth } from "@/lib/apiClient";

const auth = vi.hoisted(() => ({ user: null as { uid: string } | null, loading: false }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: "en" }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/chat/root-agent" }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
const fetchMock = vi.mocked(fetchWithAuth);
const response = (title: string) => ({ ok: true, json: async () => ({ sessions: [{ session_id: "s?1", skill_id: "other/skill", title }], next_cursor: null }) }) as Response;
beforeEach(() => { fetchMock.mockReset(); auth.user = null; auth.loading = false; });

it("loads no private conversations before sign-in", () => {
  render(<RecentConversations />);
  expect(fetchMock).not.toHaveBeenCalled();
});
it("retries failures and uses the actual session skill route", async () => {
  auth.user = { uid: "u1" };
  fetchMock.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(response("Recovered discussion"));
  render(<RecentConversations />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("link", { name: "Recovered discussion" })).toHaveAttribute("href", "/chat/other%2Fskill?session=s%3F1");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("drops a previous account's late response when the user changes", async () => {
  auth.user = { uid: "u1" };
  let finish!: (response: Response) => void;
  fetchMock.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(response("Second account"));
  const view = render(<RecentConversations />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
  auth.user = { uid: "u2" };
  view.rerender(<RecentConversations />);
  await screen.findByText("Second account");
  await act(async () => finish(response("Private first account")));
  expect(screen.queryByText("Private first account")).not.toBeInTheDocument();
  auth.user = null;
  view.rerender(<RecentConversations />);
  expect(screen.queryByText("Second account")).not.toBeInTheDocument();
});
