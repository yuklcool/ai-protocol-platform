"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { DOCUMENTS_CHANGED, documentRequest } from "@/lib/documents";
import type { Block } from "@/components/document/BlocksRenderer";
import type { ParseStatus } from "@/lib/documents";

export interface DocSummary {
  totalBlocks: number;
  headings: number;
  tables: number;
  images: number;
  changes: number;
}
export interface DocumentDetail {
  id: string;
  originalFilename: string;
  sourceFormat: string;
  parseStatus: ParseStatus;
  parseError: string | null;
  sourceUrl: string | null;
  parsedAt: string | null;
  summary: DocSummary | null;
  blocks: Block[];
}

export function useDocument(docId: string | null) {
  const { user } = useAuth();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setDoc(null);
    setError(null);
    if (!docId || !user) { setIsLoading(false); return; }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const value = await documentRequest<DocumentDetail>(`/documents/${encodeURIComponent(docId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setDoc(value);
        setError(null);
        if (value.parseStatus === "pending") timer = setTimeout(load, 2000);
      } catch (failure) {
        if (!controller.signal.aborted) setError((failure as Error).message);
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };
    const refresh = () => { clearTimeout(timer); void load(); };
    setIsLoading(true);
    void load();
    window.addEventListener(DOCUMENTS_CHANGED, refresh);
    return () => { controller.abort(); clearTimeout(timer); window.removeEventListener(DOCUMENTS_CHANGED, refresh); };
  }, [docId, user]);
  return { doc, isLoading, error };
}
