"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { DOCUMENTS_CHANGED, documentRequest, type ParseStatus } from "@/lib/documents";
export type { ParseStatus } from "@/lib/documents";

export interface Folder {
  id: string;
  name: string;
  userId: string;
  docCount: number;
  parsedCount: number;
  createdAt?: string;
}
export interface ParsedDocument {
  id: string;
  originalFilename: string;
  sourceFormat: string;
  parseStatus: ParseStatus;
  parseError: string | null;
  folderId: string;
  userId: string;
  blockCount: number | null;
  hasA2ui: boolean;
  sizeBytes?: number;
  createdAt?: string;
}

export function useDocBrowser(uid: string) {
  const { user } = useAuth();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<ParsedDocument[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision((value) => value + 1);
    window.addEventListener(DOCUMENTS_CHANGED, refresh);
    window.addEventListener("focus", refresh);
    return () => { window.removeEventListener(DOCUMENTS_CHANGED, refresh); window.removeEventListener("focus", refresh); };
  }, []);
  useEffect(() => {
    setFolders([]); setDocuments([]); setActiveFolderId(null); setIsLoading(false); setError(null);
  }, [uid, user]);
  useEffect(() => {
    if (!uid || !user) return;
    const controller = new AbortController();
    void documentRequest<{ folders: Folder[] }>("/folders", { signal: controller.signal }).then((data) => {
      if (controller.signal.aborted) return;
      setFolders(data.folders);
      setActiveFolderId((previous) => data.folders.some((folder) => folder.id === previous) ? previous : data.folders[0]?.id ?? null);
      setError(null);
    }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [uid, user, revision]);
  useEffect(() => {
    setDocuments([]);
    if (!activeFolderId || !user) { setIsLoading(false); return; }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const data = await documentRequest<{ documents: ParsedDocument[] }>(`/folders/${encodeURIComponent(activeFolderId)}/documents`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setDocuments(data.documents); setError(null);
        if (data.documents.some((doc) => doc.parseStatus === "pending")) timer = setTimeout(load, 2000);
      } catch (failure) {
        if (!controller.signal.aborted) setError((failure as Error).message);
      } finally { if (!controller.signal.aborted) setIsLoading(false); }
    };
    setIsLoading(true); void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [uid, user, activeFolderId, revision]);
  const filteredDocuments = useMemo(() => documents.filter((doc) => doc.originalFilename.toLowerCase().includes(searchQuery.trim().toLowerCase())), [documents, searchQuery]);
  return { folders, activeFolderId, documents, searchQuery, filteredDocuments, setActiveFolderId, setSearchQuery, isLoading, error };
}
