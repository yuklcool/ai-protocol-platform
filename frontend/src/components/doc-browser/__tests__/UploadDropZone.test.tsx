import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UploadDropZone } from "../UploadDropZone";
import { documentRequest } from "@/lib/documents";

vi.mock("@/lib/firebase", () => ({ getIdToken: vi.fn().mockResolvedValue("token") }));
vi.mock("@/lib/documents", () => ({ documentRequest: vi.fn(), notifyDocumentsChanged: vi.fn() }));
const request = vi.mocked(documentRequest);
const capabilities = { formats: [".txt", ".pdf", ".docx"].map((extension) => ({ extension, description: "文本" })), maxFileBytes: 25 * 1024 * 1024, maxDocuments: 10, limitations: "无 OCR" };
type FakeXhr = { open: ReturnType<typeof vi.fn>; send: ReturnType<typeof vi.fn>; abort: () => void; setRequestHeader: ReturnType<typeof vi.fn>; upload: Record<string, ((event: unknown) => void) | null>; onload?: () => void; onabort?: () => void; onerror?: () => void; responseText: string; status: number };
let requests: FakeXhr[];
beforeEach(() => {
  requests = [];
  request.mockReset().mockResolvedValue(capabilities);
  vi.spyOn(globalThis, "XMLHttpRequest").mockImplementation(() => {
    const xhr: FakeXhr = { open: vi.fn(), send: vi.fn(), abort: vi.fn(() => xhr.onabort?.()), setRequestHeader: vi.fn(), upload: {}, status: 200, responseText: JSON.stringify({ docId: "doc", originalFilename: "notes.txt", status: "parsed", blocksCount: 1 }) };
    requests.push(xhr); return xhr as unknown as XMLHttpRequest;
  });
});
afterEach(() => { vi.restoreAllMocks(); });
async function choose(names = ["notes.txt"]) {
  await waitFor(() => expect(screen.getByRole("button", { name: "添加文件或拖入此处" })).toBeEnabled());
  await userEvent.upload(screen.getByLabelText("上传对话附件"), names.map((name) => new File(["marker 119"], name, { type: "text/plain" })));
  await waitFor(() => expect(requests.length).toBeGreaterThan(0));
}
describe("对话上传", () => {
  it("读取能力矩阵，发送认证和真实表单字段", async () => {
    render(<UploadDropZone folderId="folder" skillId="skill" />); await choose();
    expect(requests[0].open).toHaveBeenCalledWith("POST", "/api/proxy/api/documents/upload");
    expect(requests[0].setRequestHeader).toHaveBeenCalledWith("Authorization", "Bearer token");
    const data = requests[0].send.mock.calls[0][0] as FormData;
    expect(data.get("folder_id")).toBe("folder"); expect(data.get("skill_id")).toBe("skill");
  });
  it("仅解析成功后标为可分析，上传完毕仍显示解析中", async () => {
    const done = vi.fn(); render(<UploadDropZone onUploadComplete={done} />); await choose();
    act(() => requests[0].upload.onload?.({}));
    expect(screen.getByText("正在解析")).toBeInTheDocument(); expect(done).not.toHaveBeenCalled();
    act(() => requests[0].onload?.());
    expect(screen.getByText("可用于分析")).toBeInTheDocument();
    expect(done).toHaveBeenCalledWith("doc", "notes.txt", expect.objectContaining({ status: "parsed" }));
  });
  it("解析失败保留文档 ID，重试解析现有文件", async () => {
    const blocked = vi.fn(); render(<UploadDropZone onBlockingChange={blocked} />); await choose();
    requests[0].responseText = JSON.stringify({docId: "bad", status: "failed", error: "没有文本层", blocksCount: 0});
    act(() => requests[0].onload?.());
    expect(screen.getByText("没有文本层")).toBeInTheDocument(); expect(blocked).toHaveBeenLastCalledWith(false);
    request.mockResolvedValueOnce({docId: "bad", parseStatus: "parsed", blockCount: 1});
    await userEvent.click(screen.getByText("重试"));
    await screen.findByText("可用于分析"); expect(blocked).toHaveBeenLastCalledWith(false);
    expect(request).toHaveBeenLastCalledWith("/documents/bad/reparse", expect.objectContaining({method: "POST"}));
  });
  it("网络失败重试成功后解除阻止发送状态", async () => {
    const blocked = vi.fn(); render(<UploadDropZone onBlockingChange={blocked} />); await choose();
    act(() => requests[0].onerror?.()); await userEvent.click(screen.getByText("重试"));
    await waitFor(() => expect(requests).toHaveLength(2)); act(() => requests[1].onload?.());
    expect(screen.queryByText("处理失败")).not.toBeInTheDocument(); expect(blocked).toHaveBeenLastCalledWith(false);
  });
  it("显示服务器拒绝原因和非 JSON 代理错误", async () => {
    render(<UploadDropZone />); await choose();
    requests[0].status = 403; requests[0].responseText = JSON.stringify({detail: {message: "账号无上传权限"}}); act(() => requests[0].onload?.());
    expect(screen.getByText("账号无上传权限")).toBeInTheDocument();
    await userEvent.click(screen.getByText("重试")); await waitFor(() => expect(requests).toHaveLength(2));
    requests[1].status = 500; requests[1].responseText = "<html>fail</html>"; act(() => requests[1].onload?.());
    expect(screen.getByText(/上传失败（500）/)).toBeInTheDocument();
  });
  it("同名文件独立处理，并限制同时上传数为三", async () => {
    render(<UploadDropZone />); await choose(["same.txt", "same.txt", "third.txt", "fourth.txt"]);
    expect(requests).toHaveLength(3); act(() => requests[0].onload?.());
    await waitFor(() => expect(requests).toHaveLength(4));
    expect(screen.getAllByText(/same.txt/)).toHaveLength(2);
  });
  it("切换会话中止上传，忽略旧请求返回", async () => {
    const done = vi.fn(); const view = render(<UploadDropZone scopeKey="a" onUploadComplete={done} />); await choose();
    view.rerender(<UploadDropZone scopeKey="b" onUploadComplete={done} />);
    expect(requests[0].abort).toHaveBeenCalled(); act(() => requests[0].onload?.()); expect(done).not.toHaveBeenCalled();
    expect(screen.queryByText(/notes.txt/)).not.toBeInTheDocument();
  });
  it("拒绝空文件，不发送请求", async () => {
    render(<UploadDropZone />); await waitFor(() => expect(screen.getByRole("button", {name:"添加文件或拖入此处"})).toBeEnabled());
    await userEvent.upload(screen.getByLabelText("上传对话附件"), new File([], "empty.txt"));
    expect(screen.getByText("文件为空。")).toBeInTheDocument(); expect(requests).toHaveLength(0);
  });
});
