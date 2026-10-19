import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSessionAttachments } from "../useSessionAttachments";
import { documentRequest, DOCUMENTS_CHANGED } from "@/lib/documents";
import type { User } from "@/lib/firebase";
vi.mock("@/lib/documents", () => ({ documentRequest: vi.fn(), DOCUMENTS_CHANGED: "documents-changed" }));
const request = vi.mocked(documentRequest);
const user = { uid: "owner" } as User;
const file = { id: "doc", filename: "附件.txt", format: "txt", included: true, parseStatus: "parsed" as const };
beforeEach(() => { request.mockReset().mockImplementation(async (path, init) => init?.method === "POST" ? {} : {documents: []}); });
describe("会话附件", () => {
  it("恢复打开顺序和勾选状态，保持未选择的标签", async () => {
    request.mockImplementation(async (path, init) => init?.method === "POST" ? {} : {documents: [file, {...file, id: "other", included: false}]});
    const { result } = renderHook(() => useSessionAttachments("a", "skill", user));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.tabs.map(({id,included})=>({id,included}))).toEqual([{id:"doc",included:true},{id:"other",included:false}]);
    expect(request.mock.calls.filter(([,init])=>init?.method==="PUT")).toHaveLength(0);
  });
  it("快速添加后清空也按顺序写入，最终持久化空选择", async () => {
    let complete: () => void = () => {};
    request.mockImplementation(async (path, init) => {
      if (init?.method === "PUT" && JSON.parse(String(init.body)).documents.length) await new Promise<void>((resolve) => { complete = resolve; });
      return {documents: []};
    });
    const { result } = renderHook(() => useSessionAttachments("a", "skill", user));
    await waitFor(() => expect(result.current.ready).toBe(true));
    act(() => result.current.setTabs([file]));
    await waitFor(() => expect(request.mock.calls.filter(([,init])=>init?.method==="PUT")).toHaveLength(1));
    act(() => result.current.setTabs([])); expect(result.current.saving).toBe(true);
    await act(async () => complete());
    await waitFor(() => expect(result.current.saving).toBe(false));
    const writes=request.mock.calls.filter(([,init])=>init?.method==="PUT");
    expect(writes.map(([,init])=>JSON.parse(String(init?.body)).documents)).toEqual([[{id:"doc",included:true}],[]]);
  });
  it("切换会话忽略旧加载结果，不显示另一会话的文件", async () => {
    let finish: (value: unknown) => void = () => {};
    request.mockImplementation(async (path, init) => path === "/sessions/a/documents" ? new Promise((resolve) => { finish=resolve; }) : {documents: []});
    const {result,rerender}=renderHook(({id})=>useSessionAttachments(id,"skill",user),{initialProps:{id:"a"}});
    await waitFor(()=>expect(request).toHaveBeenCalledWith("/sessions/a/documents",expect.anything()));
    rerender({id:"b"}); expect(result.current.tabs).toEqual([]);
    await waitFor(()=>expect(result.current.ready).toBe(true));
    await act(async()=>finish({documents:[file]})); expect(result.current.tabs).toEqual([]);
  });
  it("保存失败可重试，不能伪装为保存成功", async () => {
    request.mockImplementation(async (path,init)=>{if(init?.method==="PUT") throw new Error("保存失败"); return {documents:[]};});
    const {result}=renderHook(()=>useSessionAttachments("a","skill",user)); await waitFor(()=>expect(result.current.ready).toBe(true));
    act(()=>result.current.setTabs([file])); await waitFor(()=>expect(result.current.error).toBe("保存失败"));
    request.mockResolvedValue({documents:[]}); act(()=>result.current.retrySave());
    await waitFor(()=>expect(result.current.saving).toBe(false)); expect(result.current.error).toBeNull();
  });
  it("重新解析刷新状态时保留用户最新勾选", async () => {
    request.mockImplementation(async (path,init)=>path==="/documents/doc"?{originalFilename:"附件.txt",sourceFormat:"txt",parseStatus:"parsed",parseError:null}:{documents:[{...file,included:false,parseStatus:"failed",parseError:"旧错误"}]});
    const {result}=renderHook(()=>useSessionAttachments("a","skill",user)); await waitFor(()=>expect(result.current.ready).toBe(true));
    act(()=>window.dispatchEvent(new Event(DOCUMENTS_CHANGED)));
    await waitFor(()=>expect(result.current.tabs[0].parseStatus).toBe("parsed"));
    expect(result.current.tabs[0].included).toBe(false); expect(result.current.tabs[0].parseError).toBeNull();
  });
});
