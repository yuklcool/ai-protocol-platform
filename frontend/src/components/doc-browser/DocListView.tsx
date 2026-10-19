"use client";

import type { ParsedDocument } from "@/hooks/useDocBrowser";
import { useDocBrowser } from "@/hooks/useDocBrowser";
import { DocListFolder } from "./DocListFolder";
import { DocListSearch } from "./DocListSearch";
import { DocParseProgress } from "./DocParseProgress";

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
  const failedCount = documents.filter((d) => d.parseStatus === "failed").length;
  const docCount = documents.length;

  function handleDocClick(doc: ParsedDocument) {
    onDocClick?.(doc);
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold text-foreground">我的文件</span>
        {folders.length > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {folders.length} 个文件夹
          </span>
        )}
      </div>

      {error && <p role="alert" className="px-3 py-2 text-xs text-destructive">{error}</p>}
      {isLoading && <p role="status" className="px-3 py-2 text-xs">正在读取文件列表…</p>}
      <DocListSearch value={searchQuery} onChange={setSearchQuery} />

      <div className="min-h-0 flex-1 overflow-y-auto px-1 py-1">
        {folders.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            暂无文件。
            <br />
            在输入区添加文件即可开始分析。
          </p>
        )}

        {searchQuery.trim() !== "" ? (
          // Flat search results across all docs in the active folder
          <div className="space-y-0.5 px-1">
            {filteredDocuments.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                没有找到“{searchQuery}”
              </p>
            ) : (
              filteredDocuments.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => handleDocClick(doc)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent"
                >
                  <span className="min-w-0 flex-1 truncate">{doc.originalFilename}</span>
                </button>
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
