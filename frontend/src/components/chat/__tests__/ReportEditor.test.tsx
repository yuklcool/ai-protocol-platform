import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ReportEditor } from "../ReportEditor";

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: api }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: "en" }) }));
const saved = { report_id: "r", message_id: "m", title: "Existing title", content: "Existing text", revision: 3, updated_at: "2026-10-23T00:00:00Z" };
beforeEach(() => { api.mockReset(); });
afterEach(() => { vi.restoreAllMocks(); });

it("loads persisted content, saves the expected revision and shows confirmation", async () => {
  api.mockResolvedValueOnce({ ok: true, json: async () => ({ reports: [saved] }) });
  api.mockResolvedValueOnce({ ok: true, json: async () => ({ ...saved, content: "Edited text", revision: 4 }) });
  render(<ReportEditor sessionId="s" messageId="m" content="Original chat" />);
  fireEvent.click(screen.getByRole("button", { name: "Edit & save report" }));
  expect(await screen.findByDisplayValue("Existing text")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Report content"), { target: { value: "Edited text" } });
  fireEvent.click(screen.getByRole("button", { name: "Save report" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Report saved");
  const request = JSON.parse(api.mock.calls[1][1].body);
  expect(request).toEqual({ message_id: "m", title: "Existing title", content: "Edited text", expected_revision: 3 });
});

it("preserves the draft on a concurrent save conflict", async () => {
  api.mockResolvedValueOnce({ ok: true, json: async () => ({ reports: [] }) });
  api.mockResolvedValueOnce({ ok: false, status: 409 });
  render(<ReportEditor sessionId="s" messageId="m" content="Draft" />);
  fireEvent.click(screen.getByRole("button", { name: "Edit & save report" }));
  const save = await screen.findByRole("button", { name: "Save report" });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
  expect(await screen.findByRole("alert")).toHaveTextContent("Report changed in another window");
  expect(screen.getByLabelText("Report content")).toHaveValue("Draft");
  expect(screen.queryByText(/Report saved/)).not.toBeInTheDocument();
});

it("asks before discarding a title-only edit and preserves it when cancelled", async () => {
  api.mockResolvedValueOnce({ ok: true, json: async () => ({ reports: [saved] }) });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<ReportEditor sessionId="s" messageId="m" content="Original chat" />);
  fireEvent.click(screen.getByRole("button", { name: "Edit & save report" }));
  await screen.findByDisplayValue("Existing title");
  fireEvent.change(screen.getByLabelText("Report title"), { target: { value: "Unsaved title" } });
  fireEvent.click(screen.getByRole("button", { name: "Close report editor" }));
  expect(confirm).toHaveBeenCalledWith("Discard unsaved changes?");
  expect(screen.getByLabelText("Report title")).toHaveValue("Unsaved title");
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Close report editor" }));
  expect(screen.queryByRole("region", { name: "Report editor" })).not.toBeInTheDocument();
});
