import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantAdminPage from "@/app/admin/tenants/page";
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

describe("Root console operations", () => {
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

  it("edits tenant resource allowlists without sending retired or immutable fields", async () => {
    const tenant = {
      tenantId: "tenant-a",
      displayName: "Tenant A",
      domains: [],
      disabled: false,
      modelPolicy: {},
      quota: {},
      enabledSkills: [],
      enabledMcpServers: [],
    };
    api.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path.endsWith("/models")) return response({ models: [] });
      if (path.includes("/resources"))
        return response({
          skills: [{ id: "skill-id", label: "照明分析" }],
          mcpServers: [{ id: "map-id", label: "地图服务" }],
          tools: [],
          knowledge: [],
        });
      if (path.includes("/tenant-root/")) return response({ override: {} });
      if (init?.method === "PATCH") return response(tenant);
      return response([tenant]);
    });
    render(<TenantAdminPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const skills = await screen.findByRole("group", {
      name: "租户允许的 Skills",
    });
    fireEvent.click(await within(skills).findByLabelText("照明分析"));
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "租户允许的 MCP 服务器" }),
      ).getByLabelText("地图服务"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save tenant" }));
    await waitFor(() =>
      expect(api.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
        true,
      ),
    );
    const [, init] = api.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )!;
    const body = JSON.parse(init.body);
    expect(body.enabled_skills).toEqual(["skill-id"]);
    expect(body.enabled_mcp_servers).toEqual(["map-id"]);
    expect(body).not.toHaveProperty("tenant_id");
    expect(body).not.toHaveProperty("derived_group_tags");
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
