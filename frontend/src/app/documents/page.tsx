"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { DocListView } from "@/components/doc-browser/DocListView";
import { UploadDropZone } from "@/components/doc-browser/UploadDropZone";
import { DocumentPanel } from "@/components/document/DocumentPanel";

function DocumentsContent() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [selected, setSelected] = useState<string | null>(null);
  const preview = useRef<HTMLElement>(null);
  const library = useRef<HTMLElement>(null);
  useEffect(() => { if (selected) preview.current?.focus(); }, [selected]);
  return <main className="page-container mx-auto max-w-6xl">
    <header className="page-header page-header--compact"><h1 className="page-header__title">{zh ? "资料" : "Documents"}</h1></header>
    <div className="mb-4"><UploadDropZone compact buttonLabel={zh ? "上传资料" : "Upload documents"} scopeKey={user!.uid} skillId="root-agent" onUploadComplete={id => setSelected(id)} /></div>
    <div className={`grid gap-5 ${selected ? "lg:grid-cols-[minmax(260px,1fr)_minmax(0,2fr)]" : ""}`}>
      <section ref={library} tabIndex={-1} className="glass-panel flex h-[70dvh] min-h-80 flex-col overflow-hidden" aria-label={zh ? "资料列表" : "Document library"}><DocListView uid={user!.uid} onDocClick={doc => setSelected(doc.id)} /></section>
      {selected && <section ref={preview} tabIndex={-1} className="glass-panel order-first flex h-[70dvh] min-h-96 min-w-0 flex-col overflow-hidden lg:order-none" aria-label={zh ? "文件预览" : "Document preview"}>
        <header className="flex shrink-0 items-center justify-between gap-3 border-b p-3">
          <Link href={`/chat/root-agent?document=${encodeURIComponent(selected)}`} className="button-primary min-h-11 text-sm">{zh ? "用于新对话" : "Use in new chat"}</Link>
          <button type="button" onClick={() => { setSelected(null); library.current?.focus(); }} className="button-ghost flex h-11 w-11 items-center justify-center p-0" aria-label={zh ? "关闭预览" : "Close preview"}><X className="h-4 w-4" /></button>
        </header>
        <div className="min-h-0 flex-1"><DocumentPanel key={selected} docId={selected} /></div>
      </section>}
    </div>
  </main>;
}

export default function DocumentsPage() { return <WorkspaceGate content={DocumentsContent} />; }
