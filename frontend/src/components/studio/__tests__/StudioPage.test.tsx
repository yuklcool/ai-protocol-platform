import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Suspense, type ComponentType } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const { api, router } = vi.hoisted(() => ({
  api: vi.fn(),
  router: { replace: vi.fn(), push: vi.fn(), back: vi.fn() },
}));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: api }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { uid: "alice" }, loading: false }) }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: "en" }) }));

let StudioPage: ComponentType<{ params: Promise<{ skillId: string }> }>;
beforeAll(async () => {
  vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", "true");
  StudioPage = (await import("@/app/skills/studio/[skillId]/page")).default;
  vi.unstubAllEnvs();
});
beforeEach(() => {
  api.mockReset();
  vi.clearAllMocks();
});

const savedSkill = {
  skillId: "saved-123", ownerId: "alice", name: "my-skill", displayName: "My Skill",
  description: "", instructions: "Saved instructions", references: { "guide.md": "Reference" },
  assets: {}, accessControl: { type: "private" },
};
const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function page(skillId: string) {
  return <Suspense fallback={<p>Loading test page</p>}><StudioPage params={Promise.resolve({ skillId })} /></Suspense>;
}
async function newPage() {
  let view!: ReturnType<typeof render>;
  await act(async () => { view = render(page("new")); });
  fireEvent.change(await screen.findByLabelText("Display name"), { target: { value: "My Skill" } });
  fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Saved instructions" } });
  return view;
}
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save" }));

describe("Studio 保存与实体路由", () => {
  it("创建后 replace 到实体路由，路由生效前后再次保存均使用 PUT", async () => {
    api.mockResolvedValue(response(savedSkill));
    const view = await newPage();
    save();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/skills/studio/saved-123"));
    expect(api.mock.calls[0][0]).toBe("/api/proxy/api/skills");
    expect(api.mock.calls[0][1].method).toBe("POST");

    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Before route arrives" } });
    api.mockResolvedValue(response({ ...savedSkill, instructions: "Before route arrives" }));
    save();
    await waitFor(() => expect(screen.getByLabelText("Instructions")).toHaveValue("Before route arrives"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());
    expect(api.mock.calls[1][0]).toBe("/api/proxy/api/skills/saved-123");
    expect(api.mock.calls[1][1].method).toBe("PUT");
    expect(JSON.parse(api.mock.calls[1][1].body)).not.toHaveProperty("name");

    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "After route arrives" } });
    await act(async () => { view.rerender(page("saved-123")); });
    expect(screen.getByLabelText("Instructions")).toHaveValue("After route arrives");
    expect(api).toHaveBeenCalledTimes(2);
    api.mockResolvedValue(response({ ...savedSkill, instructions: "After route arrives" }));
    save();
    await waitFor(() => expect(api).toHaveBeenCalledTimes(3));
    expect(api.mock.calls[2][1].method).toBe("PUT");
    expect(JSON.parse(api.mock.calls[2][1].body).instructions).toBe("After route arrives");
    expect(router.replace).toHaveBeenCalledTimes(1);
  });

  it("保留请求期间的编辑和文件，收到实体路由时不重新加载覆盖 draft", async () => {
    const pending = deferred<Response>();
    api.mockReturnValueOnce(pending.promise);
    const view = await newPage();
    fireEvent.click(screen.getAllByRole("button", { name: "Add file", hidden: true })[0]);
    fireEvent.change(screen.getByLabelText("References · Filename"), { target: { value: "guide.md" } });
    fireEvent.change(screen.getByLabelText("Content"), { target: { value: "Reference" } });
    save();
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Unsaved edits" } });
    await act(async () => { pending.resolve(response(savedSkill)); });
    await act(async () => { view.rerender(page("saved-123")); });
    expect(screen.getByLabelText("Instructions")).toHaveValue("Unsaved edits");
    expect(screen.getByLabelText("Content")).toHaveValue("Reference");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(api).toHaveBeenCalledTimes(1);
  });

  it("同一轮事件中的连续保存不会重复 POST", async () => {
    const pending = deferred<Response>();
    api.mockReturnValue(pending.promise);
    await newPage();
    const button = screen.getByRole("button", { name: "Save" });
    act(() => { button.click(); button.click(); });
    expect(api).toHaveBeenCalledTimes(1);
    await act(async () => { pending.resolve(response(savedSkill)); });
    expect(router.replace).toHaveBeenCalledTimes(1);
  });

  it.each([undefined, null, "", "   ", "new", "../other", 123])("响应 ID %s 无效时不伪报成功或跳转，保留 draft", async skillId => {
    api.mockResolvedValue(response({ ...savedSkill, skillId }));
    await newPage();
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("保存响应缺少有效的 Skill ID");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Instructions")).toHaveValue("Saved instructions");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("HTTP 创建失败不跳转、不清空 draft，并可重试", async () => {
    api.mockResolvedValueOnce(response({ detail: "Rejected" }, 422));
    await newPage();
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Rejected");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Instructions")).toHaveValue("Saved instructions");
    api.mockResolvedValueOnce(response(savedSkill));
    save();
    await waitFor(() => expect(router.replace).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.map(([, init]) => init.method)).toEqual(["POST", "POST"]);
  });

  it("创建后的 PUT 失败仍保留实体 ID 和编辑，重试不会回退到 POST", async () => {
    api.mockResolvedValueOnce(response(savedSkill));
    await newPage();
    save();
    await waitFor(() => expect(router.replace).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Retry edits" } });
    api.mockResolvedValueOnce(response({ detail: "Update failed" }, 500));
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Update failed");
    expect(screen.getByLabelText("Instructions")).toHaveValue("Retry edits");
    api.mockResolvedValueOnce(response({ ...savedSkill, instructions: "Retry edits" }));
    save();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.mock.calls.map(([, init]) => init.method)).toEqual(["POST", "PUT", "PUT"]);
    expect(router.replace).toHaveBeenCalledTimes(1);
  });

  it("网络错误不跳转、不清空 draft", async () => {
    api.mockRejectedValueOnce(new Error("Offline"));
    await newPage();
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Instructions")).toHaveValue("Saved instructions");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("既有实体仍正常 GET 和 PUT，切换其他实体会加载对应内容", async () => {
    api.mockResolvedValue(response(savedSkill));
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(page("saved-123")); });
    fireEvent.change(await screen.findByLabelText("Instructions"), { target: { value: "Updated" } });
    save();
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(api.mock.calls[1][0]).toBe("/api/proxy/api/skills/saved-123");
    expect(api.mock.calls[1][1].method).toBe("PUT");
    api.mockResolvedValue(response({ ...savedSkill, skillId: "other-456", instructions: "Other content" }));
    await act(async () => { view.rerender(page("other-456")); });
    await waitFor(() => expect(screen.getByLabelText("Instructions")).toHaveValue("Other content"));
    expect(api.mock.calls[2][0]).toBe("/api/proxy/api/skills/other-456");
    expect(router.replace).not.toHaveBeenCalled();
  });
});
