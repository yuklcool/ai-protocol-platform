import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ChatSessionSummary } from "@/hooks/useSkillSessions";
import { SessionCard } from "../SessionCard";
import { fetchWithAuth } from "@/lib/apiClient";
import { notifySessionsChanged } from "@/lib/sessionEvents";

vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: "en" }) }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
vi.mock("@/lib/sessionEvents", () => ({ notifySessionsChanged: vi.fn() }));
const session: ChatSessionSummary = { session_id: "s/1", skill_id: "root-agent", owner_uid: "u1", title: "A discussion", last_message_at: "2026-10-25T00:00:00Z", first_message_at: "2026-10-25T00:00:00Z", document_ids: [], turn_count: 1, archived_at: null, is_owner: true };
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); });

it("keeps plain conversations free of a task status and folds reported plans", () => {
  const view = render(<SessionCard session={session} />);
  expect(screen.queryByText("No reported plan")).not.toBeInTheDocument();
  view.rerender(<SessionCard session={{ ...session, task_status: "completed", task_title: "File analysis" }} />);
  expect(screen.getByText("File analysis").closest("details")).not.toHaveAttribute("open");
  expect(screen.getByRole("link")).not.toHaveTextContent("Completed");
});
it("keeps the conversation on archive failure and notifies only on success", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(fetchWithAuth).mockResolvedValueOnce({ ok: false, status: 403 } as Response).mockResolvedValueOnce({ ok: true } as Response);
  render(<SessionCard session={session} />);
  fireEvent.click(screen.getByRole("button", { name: "Archive conversation" }));
  await screen.findByRole("alert");
  expect(notifySessionsChanged).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Archive conversation" }));
  await screen.findByRole("button", { name: "Archive conversation" });
  expect(fetchWithAuth).toHaveBeenLastCalledWith("/api/proxy/api/sessions/s%2F1", { method: "DELETE" });
  expect(notifySessionsChanged).toHaveBeenCalledWith({ deletedSessionId: "s/1" });
});
it("does not archive on cancelled confirmation or offer it for shared sessions", () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const view = render(<SessionCard session={session} />);
  fireEvent.click(screen.getByRole("button", { name: "Archive conversation" }));
  expect(fetchWithAuth).not.toHaveBeenCalled();
  view.rerender(<SessionCard session={{ ...session, is_owner: false }} />);
  expect(screen.queryByRole("button", { name: "Archive conversation" })).not.toBeInTheDocument();
});
