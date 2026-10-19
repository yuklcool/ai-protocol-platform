import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDocument } from "../useDocument";
import { useDocBrowser } from "../useDocBrowser";
import { documentRequest, DOCUMENTS_CHANGED } from "@/lib/documents";
const auth = vi.hoisted(() => ({ user: {uid:"owner"} as {uid:string}|null }));
vi.mock("@/contexts/AuthContext", () => ({useAuth:()=>auth}));
vi.mock("@/lib/documents",()=>({documentRequest:vi.fn(),DOCUMENTS_CHANGED:"documents-changed"}));
const request=vi.mocked(documentRequest);
beforeEach(()=>{ auth.user={uid:"owner"}; request.mockReset(); });
describe("认证文件 REST 数据流",()=>{
  it("预览响应忽略已切换文件的迟到结果，并在登出清空",async()=>{
    let finish:(value:unknown)=>void=()=>{};
    request.mockImplementation(async(path)=>path==="/documents/old"?new Promise(resolve=>{finish=resolve;}):{id:"new",parseStatus:"parsed",blocks:[]});
    const {result,rerender}=renderHook(({id})=>useDocument(id),{initialProps:{id:"old"}});
    rerender({id:"new"}); await waitFor(()=>expect(result.current.doc?.id).toBe("new"));
    await act(async()=>finish({id:"old",parseStatus:"parsed",blocks:[]})); expect(result.current.doc?.id).toBe("new");
    auth.user=null; rerender({id:"new"}); expect(result.current.doc).toBeNull();
  });
  it("文档变更通知重新读取，显示后端具体错误",async()=>{
    request.mockResolvedValue({id:"a",parseStatus:"parsed",blocks:[]}); const {result}=renderHook(()=>useDocument("a"));
    await waitFor(()=>expect(result.current.doc?.id).toBe("a"));
    request.mockRejectedValue(new Error("当前租户无权读取")); act(()=>window.dispatchEvent(new Event(DOCUMENTS_CHANGED)));
    await waitFor(()=>expect(result.current.error).toBe("当前租户无权读取"));
  });
  it("文件浏览器读取授权文件夹与轻量列表，切换账号清空",async()=>{
    request.mockImplementation(async(path)=>path==="/folders"?{folders:[{id:"folder",name:"文件",docCount:1,parsedCount:1}]}:{documents:[{id:"a",originalFilename:"报告.txt",parseStatus:"parsed"}]});
    const {result,rerender}=renderHook(()=>useDocBrowser(auth.user?.uid||""));
    await waitFor(()=>expect(result.current.documents).toHaveLength(1));
    expect(request).toHaveBeenCalledWith("/folders/folder/documents",expect.objectContaining({signal:expect.any(AbortSignal)}));
    act(()=>result.current.setSearchQuery("报告")); expect(result.current.filteredDocuments).toHaveLength(1);
    auth.user=null; rerender(); expect(result.current.documents).toEqual([]); expect(result.current.isLoading).toBe(false);
  });
});
