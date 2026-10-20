import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UsagePanel } from "../UsagePanel";

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: api }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { uid: "admin", email: "admin@local.test" },
    loading: false,
  }),
}));
vi.mock("@/hooks/useAdminScope", () => ({
  useAdminScope: () => ({
    isPlatform: true,
    isAdmin: true,
    state: "platform",
    tenantIds: [],
  }),
}));
const response = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
});
beforeEach(() => {
  api.mockReset();
});

describe("User usage accounting", () => {
  it("shows persisted tokens and estimates while exposing missing pricing", async () => {
    api.mockResolvedValue(
      response({
        totals: {
          calls: 2,
          inputTokens: 123,
          outputTokens: 45,
          estimatedCostUsd: 0.03,
          unpricedCalls: 1,
        },
        users: [],
        models: [],
      }),
    );
    render(<UsagePanel />);
    expect(await screen.findByText("123")).toBeVisible();
    expect(screen.getByText("$0.030000")).toBeVisible();
    expect(screen.getByText(/1 calls have no known pricing/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Usage time range"), {
      target: { value: "7" },
    });
    await waitFor(() =>
      expect(
        api.mock.calls.some(([path]) => String(path).includes("days=7")),
      ).toBe(true),
    );
  });
});
