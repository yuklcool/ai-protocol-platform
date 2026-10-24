"use client";

import type { Folder, ParsedDocument } from "@/hooks/useDocBrowser";
import { DocListItem } from "./DocListItem";

interface DocListFolderProps {
  folder: Folder;
  documents: ParsedDocument[];
  isActive: boolean;
  isLoading?: boolean;
  onSelect: (folderId: string | null) => void;
  onDocClick: (doc: ParsedDocument) => void;
}

export function DocListFolder({
  folder,
  documents,
  isActive,
  isLoading = false,
  onSelect,
  onDocClick,
}: DocListFolderProps) {
  const open = isActive;

  return (
    <div>
      <button
        type="button"
        onClick={() => onSelect(open ? null : folder.id)}
        className={`flex min-h-11 w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${isActive ? "bg-accent" : ""}`}
        aria-expanded={open}
      >
        <svg
          className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 12 12"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <svg
          className="h-3.5 w-3.5 shrink-0 text-amber-500"
          viewBox="0 0 16 16"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M1.5 3.5A1 1 0 012.5 2.5h3.879a1 1 0 01.707.293L8.5 4.5H13.5a1 1 0 011 1V12a1 1 0 01-1 1h-11a1 1 0 01-1-1V3.5z" />
        </svg>
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
          {folder.name}
        </span>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {folder.docCount}
        </span>
      </button>

      {open && (
        <div className="ml-5 mt-0.5 space-y-0.5">
          {!isLoading && documents.length === 0 && (
            <p className="px-2 py-1 text-xs text-muted-foreground">
              暂无文件
            </p>
          )}
          {documents.map((doc) => (
            <DocListItem key={doc.id} doc={doc} onClick={onDocClick} />
          ))}
        </div>
      )}
    </div>
  );
}
