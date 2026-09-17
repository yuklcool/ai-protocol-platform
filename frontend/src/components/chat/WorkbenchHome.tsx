// Workspace tab Home: navigation index for session results and the active document.

"use client";

import type { A2uiArtifactEntry } from "@/providers/SurfaceRegistry";
import { WorkbenchIndex } from "./WorkbenchIndex";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

export interface WorkbenchHomeProps {
  artifacts: A2uiArtifactEntry[];
  onOpen: (surfaceId: string) => void;
  openDocId?: string | null;
  onOpenDocument?: () => void;
}

export function WorkbenchHome({ artifacts, onOpen, openDocId, onOpenDocument }: WorkbenchHomeProps) {
  const { locale } = useI18n();
  const hasIndex = artifacts.length > 0 || Boolean(openDocId);

  if (!hasIndex) {
    return (
      <p className="p-4 text-sm text-muted-foreground" data-testid="home-empty">
        {translateChat(locale, "workbench.homeEmpty")}
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      {artifacts.length > 0 && (
        <WorkbenchIndex
          artifacts={[...artifacts].reverse()}
          onOpen={onOpen}
          heading={translateChat(locale, "workbench.results")}
        />
      )}
      {openDocId && (
        <div className="px-3 pb-3">
          <button
            type="button"
            onClick={onOpenDocument}
            className="group flex w-full items-start gap-3 rounded-lg border border-border bg-muted/10 px-3 py-2.5 text-left transition-colors hover:border-primary/50 hover:bg-muted/30"
            data-testid="home-document-row"
          >
            <span className="mt-0.5 shrink-0 rounded-md bg-primary/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-primary">
              {translateChat(locale, "workbench.document")}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground">
                {translateChat(locale, "workbench.openDocument")}
              </span>
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                {translateChat(locale, "workbench.documentDescription")}
              </span>
            </span>
            <span aria-hidden className="mt-0.5 text-xs text-muted-foreground/50 group-hover:text-primary">
              {translateChat(locale, "workbench.open")}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
