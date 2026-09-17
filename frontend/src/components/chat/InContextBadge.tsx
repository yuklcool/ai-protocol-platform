"use client";

import type { DocTabData } from "@/components/doc-browser/DocTab";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface InContextBadgeProps {
  openTabs: DocTabData[];
  includedDocIds: string[];
}

/** Visible confirmation of the documents included in the next agent turn. */
export function InContextBadge({ openTabs, includedDocIds }: InContextBadgeProps) {
  const { locale } = useI18n();
  if (includedDocIds.length === 0) return null;
  const includedTabs = openTabs.filter((t) => includedDocIds.includes(t.id));
  const label =
    includedTabs.length === 1
      ? translateChat(locale, "context.willProcessOne", { file: includedTabs[0].filename })
      : translateChat(locale, "context.willProcessMany", { count: includedDocIds.length });
  return (
    <div className="mb-2 flex items-center gap-2 px-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-primary/70" aria-hidden />
      <span className="truncate">{label}</span>
    </div>
  );
}
