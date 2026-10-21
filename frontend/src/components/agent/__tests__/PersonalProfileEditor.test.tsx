import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { PersonalProfileEditor } from "../PersonalProfileEditor";
const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: api }));
const response = (body: unknown) => ({ ok: true, json: async () => body });
beforeEach(() => { api.mockReset(); });
it("saves a user's Skill and personal information without role or tool grants", async () => {
  api.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.includes("/skills")) return response([{ skillId: "private", displayName: "Personal Skill" }]);
    return response(init?.body ? JSON.parse(String(init.body)) : { skills: [], information: "" });
  });
  render(<PersonalProfileEditor uid="admin" email="admin@example.com" />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "Personal Skill" }));
  fireEvent.change(screen.getByLabelText("个人信息与偏好"), { target: { value: "My preferences" } });
  fireEvent.click(screen.getByRole("button", { name: "保存个人配置" }));
  await screen.findByText("个人配置已保存，下次调用立即生效。");
  const [path, init] = api.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(path).toContain("/admin/accounts/admin%40example.com/profile");
  expect(api).toHaveBeenCalledWith("/api/proxy/api/admin/accounts/admin%40example.com/skills", undefined);
  expect(JSON.parse(init.body)).toEqual({ skills: ["private"], information: "My preferences" });
});
it("requests ownerId and only offers this user's Skills when ownership is returned", async () => {
  const uid = "alice+work@example.com";
  api.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.includes("/skills")) return response([
      { skillId: "owned", name: "Owned Skill", ownerId: uid },
      { skillId: "shared", name: "Shared Skill", ownerId: "bob", accessControl: { type: "public" } },
      { skillId: "platform", name: "Platform Skill", ownerId: "aitana-platform" },
      { skillId: "legacy", name: "Compact Skill" },
    ]);
    return response(init?.body ? JSON.parse(String(init.body)) : { skills: [], information: "" });
  });
  render(<PersonalProfileEditor uid={uid} />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "Owned Skill" }));
  expect(api).toHaveBeenCalledWith(`/api/proxy/api/skills?ownerId=${encodeURIComponent(uid)}&limit=200`, undefined);
  expect(api.mock.calls.some(([path]) => path.includes("owner_id="))).toBe(false);
  expect(screen.queryByRole("checkbox", { name: "Shared Skill" })).toBeNull();
  expect(screen.queryByRole("checkbox", { name: "Platform Skill" })).toBeNull();
  expect(screen.getByRole("checkbox", { name: "Compact Skill" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保存个人配置" }));
  await screen.findByText("个人配置已保存，下次调用立即生效。");
  const [path, init] = api.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(path).toBe("/api/proxy/api/auth/profile");
  expect(JSON.parse(init.body)).toEqual({ skills: ["owned"], information: "" });
});
it("does not offer a blank save form after loading fails and supports retry", async () => {
  api.mockRejectedValueOnce(new Error("Offline"));
  api.mockResolvedValue(response([]));
  render(<PersonalProfileEditor uid="alice" />);
  await screen.findByText("Offline");
  expect(screen.queryByRole("button", { name: "保存个人配置" })).toBeNull();
  api.mockImplementation(async (path: string) => response(path.includes("/skills") ? [] : { skills: [], information: "Saved information" }));
  fireEvent.click(screen.getByRole("button", { name: "重试加载" }));
  await waitFor(() => expect(screen.getByLabelText("个人信息与偏好")).toHaveValue("Saved information"));
});
