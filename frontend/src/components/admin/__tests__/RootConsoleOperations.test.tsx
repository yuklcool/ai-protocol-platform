import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ToolPermissionsPage from "@/app/admin/tool-permissions/page";
import TenantAdminPage from "@/app/admin/tenants/page";
import { LocalAccountsPanel } from "../LocalAccountsPanel";
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
    domains: [],
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

describe("Root console operations", () => {
  it("saves a stable tenant rule using the backend tenant type", async () => {
    api.mockResolvedValue(response([]));
    render(<ToolPermissionsPage />);
    fireEvent.change(await screen.findByLabelText("Stable tenant ID"), {
      target: { value: "tenant-a" },
    });
    fireEvent.change(screen.getByLabelText(/Allowed tools/), {
      target: { value: "list_documents, get_document_content" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() =>
      expect(api.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(
        true,
      ),
    );
    const [path, init] = api.mock.calls.find(
      ([, options]) => options?.method === "PUT",
    )!;
    expect(path).toContain("tenant%3Atenant-a");
    expect(JSON.parse(init.body)).toEqual({
      type: "tenant",
      tools: ["list_documents", "get_document_content"],
      denied: [],
    });
    expect(
      await screen.findByText("Permissions saved; cache refreshed."),
    ).toBeVisible();
  });

  it("creates a domainless stable tenant without using the legacy clients API", async () => {
    api.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path.endsWith("/models")) return response({ models: [] });
      if (path.includes("/resources"))
        return response({
          skills: [],
          tools: [],
          mcpServers: [],
          knowledge: [],
        });
      if (path.includes("/tenant-root/")) return response({ override: {} });
      if (init?.method === "POST")
        return response({
          config: {
            tenantId: "tenant-a",
            displayName: "Tenant A",
            domains: [],
            disabled: false,
            quota: {},
            modelPolicy: {},
          },
        });
      return response([]);
    });
    render(<TenantAdminPage />);
    fireEvent.click(await screen.findByRole("button", { name: "New tenant" }));
    fireEvent.change(screen.getByLabelText("Stable tenant ID"), {
      target: { value: "tenant-a" },
    });
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Tenant A" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save tenant" }));
    await screen.findByText("Tenant saved.");
    const [path, init] = api.mock.calls.find(
      ([, options]) => options?.method === "POST",
    )!;
    expect(path).toBe("/api/proxy/api/admin/tenants");
    expect(JSON.parse(init.body).tenant_id).toBe("tenant-a");
    expect(JSON.parse(init.body).domains).toEqual([]);
    expect(
      api.mock.calls.every(([url]) => !String(url).includes("/clients")),
    ).toBe(true);
  });

  it("clears the account password after a successful creation", async () => {
    api.mockImplementation(async (path: string, init?: RequestInit) =>
      response(
        path.endsWith("/tenants")
          ? [{ tenantId: "tenant-a", displayName: "Tenant A", disabled: false }]
          : init?.method === "POST"
            ? {}
            : [],
      ),
    );
    render(<LocalAccountsPanel onSelect={vi.fn()} />);
    await screen.findByRole("option", { name: "Tenant A" });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "new@local.test" },
    });
    fireEvent.change(screen.getByLabelText(/Initial password/), {
      target: { value: "disposable-test-password" },
    });
    fireEvent.change(screen.getByLabelText("Tenant"), {
      target: { value: "tenant-a" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Create account" }).closest("form")!,
    );
    await screen.findByText("Account created.");
    expect(screen.getByLabelText(/Initial password/)).toHaveValue("");
    const [, init] = api.mock.calls.find(
      ([, options]) => options?.method === "POST",
    )!;
    expect(JSON.parse(init.body).tenant_id).toBe("tenant-a");
  });

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
        tenants: [],
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
