"use client";

import { useState } from "react";
import { documentRequest, notifyDocumentsChanged } from "@/lib/documents";

import { useDocument, type DocumentDetail } from "@/hooks/useDocument";
import type { ParseStatus } from "@/hooks/useDocBrowser";
import { DocumentHeader } from "./DocumentHeader";
import { DocumentFooter } from "./DocumentFooter";
import { DocumentViewer } from "./DocumentViewer";

interface DocumentPanelProps {
  docId: string;
}

function isPendingStatus(status: ParseStatus): boolean {
  return status === "pending" || status === "pending_ai_extraction";
}

function pickCaption(doc: DocumentDetail | null): string {
  if (!doc) return "正在读取文件…";
  if (isPendingStatus(doc.parseStatus)) return "正在解析文件…";
  return "正在读取内容…";
}

function Skeleton({ caption }: { caption: string }) {
  return (
    <div className="flex h-full flex-col" data-testid="doc-panel-loading">
      <div className="h-10 animate-pulse border-b bg-muted/40" />
      <div className="flex-1 space-y-3 p-3">
        <div className="text-xs text-muted-foreground">{caption}</div>
        {[80, 60, 90, 50].map((w) => (
          <div
            key={w}
            className="h-3 animate-pulse rounded bg-muted"
            style={{ width: `${w}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function TerminalMessage({
  doc,
  message,
}: {
  doc: DocumentDetail;
  message: string;
}) {
  const [retrying, setRetrying] = useState(false);
  const [failure, setFailure] = useState("");
  async function retry() {
    setRetrying(true); setFailure("");
    try {
      await documentRequest(`/documents/${encodeURIComponent(doc.id)}/reparse`, { method: "POST" });
      notifyDocumentsChanged();
    } catch (error) { setFailure((error as Error).message); }
    finally { setRetrying(false); }
  }
  return (
    <div className="flex h-full flex-col">
      <DocumentHeader doc={doc} />
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
        <div className="space-y-3 text-center"><p>{message}</p>{failure && <p role="alert">{failure}</p>}<button type="button" disabled={retrying} onClick={() => void retry()} className="rounded border px-3 py-1">{retrying ? "正在解析…" : "重试解析"}</button></div>
      </div>
    </div>
  );
}

export function DocumentPanel({ docId }: DocumentPanelProps) {
  const { doc, isLoading, error } = useDocument(docId);

  if (isLoading || (!doc && !error)) {
    return <Skeleton caption={pickCaption(doc)} />;
  }

  if (error || !doc) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {error ?? "无法读取文件预览，请重试。"}
      </div>
    );
  }

  if (doc.parseStatus === "failed" || doc.parseStatus === "pending_ai_extraction") {
    return (
      <TerminalMessage
        doc={doc}
        message={doc.parseError ?? "文件无法读取，请重试解析或重新上传。"}
      />
    );
  }

  if (isPendingStatus(doc.parseStatus)) {
    return <Skeleton caption="正在解析文件…" />;
  }

  if (!doc.blocks || doc.blocks.length === 0) {
    return (
      <TerminalMessage doc={doc} message="没有可读取的内容。" />
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-muted/10">
      <DocumentHeader doc={doc} />
      <DocumentViewer doc={doc} />
      {doc.summary && <DocumentFooter summary={doc.summary} />}
    </div>
  );
}
