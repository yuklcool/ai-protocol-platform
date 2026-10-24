"use client";

import type { ParsedDocument } from "@/hooks/useDocBrowser";
import { useDocBrowser } from "@/hooks/useDocBrowser";
import { DocListFolder } from "./DocListFolder";
import { DocListSearch } from "./DocListSearch";
import { DocParseProgress } from "./DocParseProgress";
import { DocListItem } from "./DocListItem";

interface DocListViewProps {
  uid: string;
  onDocClick?: (doc: ParsedDocument) => void;
}

export function DocListView({ uid, onDocClick }: DocListViewProps) {
  const {
    folders,
    activeFolderId,
    documents,
    searchQuery,
    filteredDocuments,
    setActiveFolderId,
    setSearchQuery,
    error,
    isLoading,
  } = useDocBrowser(uid);

  // Stats for active folder
  const activeFolder = folders.find((f) => f.id === activeFolderId) ?? null;
  const parsedCount = documents.filter((d) => d.parseStatus === "parsed").length;
  const failedCount = documents.filter((d) => d.parseStatus === "failed" || d.parseStatus === "pending_ai_extraction").length;
  const docCount = documents.length;

  function handleDocClick(doc: ParsedDocument) {
    onDocClick?.(doc);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {error && <p role="alert" className="px-3 py-2 text-xs text-destructive">{error}</p>}
      {isLoading && <p role="status" className="px-3 py-2 text-xs">正在读取文件列表…</p>}
      <DocListSearch value={searchQuery} onChange={setSearchQuery} />
      {folders.length > 0 && <p className="px-4 pb-2 text-xs text-muted-foreground">{folders.length} 个文件夹 · 搜索当前文件夹内的文件</p>}

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-1" data-resource-scroll="files">
        {!error && !isLoading && folders.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            暂无文件。
            <br />
            在输入区添加文件即可开始分析。
          </p>
        )}

        {!error && !isLoading && searchQuery.trim() !== "" ? (
          // Flat search results across all docs in the active folder
          <div className="space-y-0.5 px-1">
            {filteredDocuments.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                没有找到“{searchQuery}”
              </p>
            ) : (
              filteredDocuments.map((doc) => (
                <DocListItem key={doc.id} doc={doc} onClick={handleDocClick} />
              ))
            )}
          </div>
        ) : (
          // Folder accordion view
          <div className="space-y-0.5 px-1">
            {folders.map((folder) => (
              <DocListFolder
                key={folder.id}
                folder={folder}
                documents={folder.id === activeFolderId ? filteredDocuments : []}
                isActive={folder.id === activeFolderId}
                isLoading={isLoading && folder.id === activeFolderId}
                onSelect={setActiveFolderId}
                onDocClick={handleDocClick}
              />
            ))}
          </div>
        )}
      </div>

      {activeFolder && (
        <DocParseProgress parsedCount={parsedCount} failedCount={failedCount} docCount={docCount} />
      )}
    </div>
  );
}
