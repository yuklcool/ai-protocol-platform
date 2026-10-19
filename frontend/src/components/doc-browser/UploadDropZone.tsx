"use client";

import { useEffect, useRef, useState } from "react";
import { getIdToken } from "@/lib/firebase";
import { documentRequest, notifyDocumentsChanged, type DocumentCapabilities, type UploadResult } from "@/lib/documents";

type UploadJob = {
  id: string;
  file: File;
  status: "queued" | "uploading" | "processing" | "done" | "error" | "cancelled";
  pct: number;
  error?: string;
  docId?: string;
};
interface UploadDropZoneProps {
  folderId?: string;
  skillId?: string;
  scopeKey?: string | null;
  attachedCount?: number;
  disabled?: boolean;
  onUploadComplete?: (docId: string, filename: string, result: UploadResult) => void;
  onBusyChange?: (busy: boolean) => void;
  onBlockingChange?: (blocked: boolean) => void;
}

export function UploadDropZone({ folderId = "", skillId = "", scopeKey = null, attachedCount = 0, disabled = false, onUploadComplete, onBusyChange, onBlockingChange }: UploadDropZoneProps) {
  const [capabilities, setCapabilities] = useState<DocumentCapabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [dragging, setDragging] = useState(false);
  const queue = useRef<UploadJob[]>([]);
  const active = useRef(new Map<string, XMLHttpRequest | null>());
  const generation = useRef(0);
  const reparses = useRef(new Map<string, AbortController>());
  const input = useRef<HTMLInputElement>(null);
  const callbacks = useRef({ onUploadComplete, onBusyChange });
  callbacks.current = { onUploadComplete, onBusyChange };
  useEffect(() => {
    onBlockingChange?.(jobs.some((job) => job.status === "error" && !job.docId));
    onBusyChange?.(jobs.some((job) => ["queued", "uploading", "processing"].includes(job.status)));
  }, [jobs, onBlockingChange, onBusyChange]);

  useEffect(() => {
    const controller = new AbortController();
    void documentRequest<DocumentCapabilities>("/documents/capabilities", { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setCapabilities(data);
    }).catch((failure) => { if (!controller.signal.aborted) setCapabilityError(failure.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const version = ++generation.current;
    const requests = active.current;
    const controllers = reparses.current;
    setJobs([]);
    return () => {
      generation.current = version + 1;
      queue.current = [];
      for (const request of requests.values()) request?.abort();
      requests.clear();
      for (const controller of controllers.values()) controller.abort();
      controllers.clear();
      callbacks.current.onBusyChange?.(false);
    };
  }, [scopeKey]);

  function update(id: string, patch: Partial<UploadJob>) {
    setJobs((previous) => previous.map((job) => job.id === id ? { ...job, ...patch } : job));
  }
  function receive(job: UploadJob, result: UploadResult) {
    if (!result.docId || !["parsed", "failed", "pending", "pending_ai_extraction"].includes(result.status)) throw new Error("上传响应不完整，请重试。");
    update(job.id, { docId: result.docId, pct: 100, status: result.status === "parsed" ? "done" : "error", error: result.error || (result.status !== "parsed" ? "文件尚不可读取，请重试解析或移除。" : undefined) });
    callbacks.current.onUploadComplete?.(result.docId, result.originalFilename || job.file.name, result);
    notifyDocumentsChanged();
  }
  async function upload(job: UploadJob, version: number) {
    update(job.id, { status: "uploading", pct: 0, error: undefined });
    const token = await getIdToken();
    if (generation.current !== version || !active.current.has(job.id)) return;
    const data = new FormData();
    data.append("file", job.file);
    if (folderId) data.append("folder_id", folderId);
    if (skillId) data.append("skill_id", skillId);
    await new Promise<void>((resolve) => {
      const xhr = new XMLHttpRequest();
      active.current.set(job.id, xhr);
      xhr.open("POST", "/api/proxy/api/documents/upload");
      xhr.timeout = 120000;
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (event) => {
        if (generation.current === version && event.lengthComputable) update(job.id, { pct: Math.round(event.loaded / event.total * 100) });
      };
      xhr.upload.onload = () => { if (generation.current === version) update(job.id, { status: "processing", pct: 100 }); };
      xhr.onload = () => {
        if (generation.current !== version) { resolve(); return; }
        try {
          let response;
          try { response = JSON.parse(xhr.responseText); } catch { throw new Error(xhr.status >= 200 && xhr.status < 300 ? "上传响应不完整，请重试。" : `上传失败（${xhr.status}），请重试。`); }
          if (xhr.status < 200 || xhr.status >= 300) {
            throw new Error(typeof response.detail === "string" ? response.detail : response.detail?.message || `上传失败（${xhr.status}）。`);
          }
          receive(job, response as UploadResult);
        } catch (failure) { update(job.id, { status: "error", error: (failure as Error).message }); }
        resolve();
      };
      const fail = (reason: string) => { if (generation.current === version) update(job.id, { status: "error", error: reason }); resolve(); };
      xhr.onerror = () => fail("网络中断，文件未附加到对话，请重试。");
      xhr.ontimeout = () => fail("上传或解析超时，请重试或拆分文件。");
      xhr.onabort = () => { if (generation.current === version) update(job.id, { status: "cancelled", error: undefined }); resolve(); };
      xhr.send(data);
    });
  }
  function drain() {
    const version = generation.current;
    while (queue.current.length && active.current.size < 3) {
      const job = queue.current.shift()!;
      active.current.set(job.id, null);
      void upload(job, version).catch((failure) => {
        if (generation.current === version) update(job.id, { status: "error", error: failure.message });
      }).finally(() => {
        if (generation.current !== version) return;
        active.current.delete(job.id);
        drain();
      });
    }
  }
  function enqueue(files: File[]) {
    if (!capabilities || disabled) return;
    const remaining = capabilities.maxDocuments - attachedCount - queue.current.length - active.current.size;
    if (files.length > remaining) { setCapabilityError(`每个会话最多打开 ${capabilities.maxDocuments} 个文件，请先移除部分附件。`); return; }
    setCapabilityError("");
    const next = files.map((file): UploadJob => {
      const extension = "." + file.name.split(".").pop()?.toLowerCase();
      const error = !capabilities.formats.some((format) => format.extension === extension) ? "暂不支持此格式；图片和扫描件暂不支持识别。" : file.size === 0 ? "文件为空。" : file.size > capabilities.maxFileBytes ? "文件超过 25 MB，请拆分后上传。" : undefined;
      return { id: crypto.randomUUID(), file, pct: 0, status: error ? "error" : "queued", error };
    });
    setJobs((previous) => [...previous, ...next]);
    queue.current.push(...next.filter((job) => job.status === "queued"));
    drain();
  }
  function cancel(job: UploadJob) {
    queue.current = queue.current.filter((entry) => entry.id !== job.id);
    active.current.get(job.id)?.abort();
    reparses.current.get(job.id)?.abort();
    if (active.current.get(job.id) === null) active.current.delete(job.id);
    update(job.id, { status: "cancelled" });
  }
  async function retry(job: UploadJob) {
    if (!job.docId) { setJobs((previous) => previous.filter((entry) => entry.id !== job.id)); enqueue([job.file]); return; }
    const version = generation.current;
    const controller = new AbortController();
    reparses.current.set(job.id, controller);
    update(job.id, { status: "processing", error: undefined });
    try {
      const response = await documentRequest<{ docId: string; parseStatus: UploadResult["status"]; blockCount: number; parseError: string | null }>(`/documents/${encodeURIComponent(job.docId)}/reparse`, { method: "POST", signal: controller.signal });
      if (generation.current === version && !controller.signal.aborted) receive(job, { docId: response.docId, status: response.parseStatus, error: response.parseError, blocksCount: response.blockCount, originalFilename: job.file.name });
    } catch (failure) { if (generation.current === version && !controller.signal.aborted) update(job.id, { status: "error", error: (failure as Error).message }); }
    finally { reparses.current.delete(job.id); }
  }
  return (
    <div className="space-y-2 glass-panel p-3" onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); enqueue(Array.from(event.dataTransfer.files)); }}>
      <button type="button" disabled={!capabilities || disabled} onClick={() => input.current?.click()} className="rounded border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50">{dragging ? "松开文件开始上传" : "添加文件或拖入此处"}</button>
      <input ref={input} aria-label="上传对话附件" type="file" multiple className="hidden" accept={capabilities?.formats.map((format) => format.extension).join(",")} onChange={(event) => { if (event.target.files) enqueue(Array.from(event.target.files)); event.target.value = ""; }} />
      <p className="text-[11px] text-muted-foreground">TXT、Markdown、CSV、文本 PDF、DOCX、XLSX、PPTX；单文件 25 MB，每轮最多 10 个。图片和扫描件暂不支持识别。</p>
      {capabilityError && <p role="alert" className="text-xs text-destructive">{capabilityError}</p>}
      <ul className="space-y-1" aria-label="文件处理状态">
        {jobs.map((job) => <li key={job.id} className="flex flex-wrap items-center gap-2 text-xs">
          <span className="min-w-0 truncate">{job.file.name} · {(job.file.size / 1024).toFixed(1)} KB</span>
          <span role="status">{job.status === "queued" ? "等待上传" : job.status === "uploading" ? `正在上传 ${job.pct}%` : job.status === "processing" ? "正在解析" : job.status === "done" ? "可用于分析" : job.status === "cancelled" ? "已取消" : "处理失败"}</span>
          {job.error && <span className="text-destructive">{job.error}</span>}
          {["queued", "uploading", "processing"].includes(job.status) && <button type="button" onClick={() => cancel(job)}>取消</button>}
          {job.status === "error" && <button type="button" onClick={() => void retry(job)}>重试</button>}
          {["error", "cancelled", "done"].includes(job.status) && <button type="button" onClick={() => setJobs((previous) => previous.filter((entry) => entry.id !== job.id))}>移除此记录</button>}
        </li>)}
      </ul>
    </div>
  );
}
