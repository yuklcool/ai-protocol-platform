"use client";

import { useState } from "react";
import type { DocumentDetail } from "@/hooks/useDocument";
import { fetchWithAuth } from "@/lib/apiClient";

export function DocumentHeader({ doc }: { doc: DocumentDetail }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function download() {
    setBusy(true); setError("");
    try {
      const response = await fetchWithAuth(`/api/proxy/api/documents/${encodeURIComponent(doc.id)}/download`);
      if (!response.ok) throw new Error(`下载失败（${response.status}），请重试。`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = doc.originalFilename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <div className="border-b px-3 py-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="min-w-0 flex-1 truncate font-medium">{doc.originalFilename}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">{doc.sourceFormat}</span>
        <button type="button" disabled={busy} onClick={() => void download()} className="text-xs text-primary">{busy ? "正在下载…" : "下载原文件"}</button>
      </div>
      {error && <p role="alert" className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
