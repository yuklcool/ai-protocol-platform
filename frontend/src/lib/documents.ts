import { fetchWithAuth } from "@/lib/apiClient";

export const DOCUMENTS_CHANGED = "aip:documents-changed";
export type ParseStatus = "pending" | "pending_ai_extraction" | "parsed" | "failed";
export type UploadResult = {
  docId: string;
  originalFilename: string;
  status: ParseStatus;
  error?: string | null;
  blocksCount: number;
};
export type DocumentCapabilities = {
  formats: { extension: string; description: string }[];
  maxFileBytes: number;
  maxDocuments: number;
  limitations: string;
};

export async function documentRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithAuth(`/api/proxy/api${path}`, init);
  if (!response.ok) {
    let reason = `文件请求失败（${response.status}），请重试。`;
    try {
      const { detail } = await response.json();
      if (typeof detail === "string") reason = detail;
      else if (typeof detail?.message === "string") reason = detail.message;
    } catch { /* Keep the status when a proxy returns a non-JSON error. */ }
    throw new Error(reason);
  }
  return response.json() as Promise<T>;
}

export function notifyDocumentsChanged() {
  window.dispatchEvent(new Event(DOCUMENTS_CHANGED));
}
