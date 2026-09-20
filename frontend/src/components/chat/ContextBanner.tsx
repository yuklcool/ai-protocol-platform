"use client";

import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

export interface ActiveDocumentContext {
  folderName: string;
  docCount: number;
}

interface ContextBannerProps {
  context: ActiveDocumentContext | null;
}

export function ContextBanner({ context }: ContextBannerProps) {
  const { locale } = useI18n();
  if (!context) return null;

  const key = context.docCount === 1 ? "context.analyzingOne" : "context.analyzingMany";
  const label = translateChat(locale, key, {
    count: context.docCount,
    folder: context.folderName,
  });

  return (
    <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
      <svg
        className="h-3.5 w-3.5 shrink-0 text-primary"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path
          d="M2 4a1 1 0 011-1h3.5l1.5 2H13a1 1 0 011 1v6a1 1 0 01-1 1H3a1 1 0 01-1-1V4z"
          strokeLinejoin="round"
        />
      </svg>
      <span>{label}</span>
    </div>
  );
}
