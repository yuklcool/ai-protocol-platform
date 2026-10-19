import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GroupsPage from "@/app/admin/groups/page";
import UsersPage from "@/app/admin/users/page";

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: api }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { uid: "admin" }, loading: false }),
}));
vi.mock("@/hooks/useAdminScope", () => ({
  useAdminScope: () => ({ isPlatform: true, isAdmin: true, state: "platform" }),
}));
const response = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
});
beforeEach(() => {
  api.mockReset();
});

describe("权限组配置流程", () => {
  it("选择实际资源保存组，不要求手输标签或资源编号", async () => {
    api.mockImplementation(async (url: string) => {
      if (url.endsWith("/tenants"))
        return response([
          { tenantId: "tenant-a", displayName: "租户 A", disabled: false },
        ]);
      if (url.includes("/resources?"))
        return response({
          skills: [{ id: "skill-id", label: "照明分析" }],
          mcpServers: [{ id: "mcp-id", label: "地图服务" }],
        });
      return response([]);
    });
    render(<GroupsPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "新建权限组" })).toBeEnabled(),
    );
    fireEvent.click(await screen.findByRole("button", { name: "新建权限组" }));
    await screen.findByLabelText("照明分析");
    fireEvent.change(screen.getByLabelText("组名称"), {
      target: { value: "照明人员" },
    });
    fireEvent.click(screen.getByLabelText("照明分析"));
    fireEvent.click(screen.getByLabelText("地图服务"));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
        true,
      ),
    );
    const [, init] = api.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    expect(JSON.parse(init.body)).toMatchObject({
      tenantId: "tenant-a",
      skills: ["skill-id"],
      mcpServers: ["mcp-id"],
      role: "member",
    });
    expect(JSON.parse(init.body)).not.toHaveProperty("grants");
  });

  it("用户只看到同租户权限组，保存成员关系时不写入旧标签", async () => {
    api.mockImplementation(async (url: string) => {
      if (url.endsWith("/provider")) return response({ backend: "local-jwt" });
      if (url.endsWith("/tenants"))
        return response([
          { tenantId: "tenant-a", displayName: "租户 A", disabled: false },
        ]);
      if (url.endsWith("/groups"))
        return response([
          { id: "group-a", tenantId: "tenant-a", label: "照明人员" },
          { id: "foreign", tenantId: "tenant-b", label: "其他租户" },
        ]);
      return response([
        {
          email: "user@example.test",
          uid: "user",
          tenantId: "tenant-a",
          permissionGroupIds: [],
          disabled: false,
          platformAdmin: false,
        },
      ]);
    });
    render(<UsersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByLabelText("照明人员"));
    expect(screen.queryByLabelText("其他租户")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(api.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
        true,
      ),
    );
    const [, init] = api.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )!;
    expect(JSON.parse(init.body)).toEqual({
      disabled: false,
      permission_group_ids: ["group-a"],
    });
  });

  it("OIDC 只管理关联账号授权，不提供本地创建密码入口", async () => {
    api.mockImplementation(async (url: string) =>
      response(url.endsWith("/provider") ? { backend: "oidc" } : []),
    );
    render(<UsersPage />);
    await screen.findByText(/登录身份和密码由 OIDC/);
    expect(
      screen.queryByRole("button", { name: "新建用户" }),
    ).not.toBeInTheDocument();
  });
});
