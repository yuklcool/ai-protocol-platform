// Workshop W5b — AG-UI: text events → chat bubbles
// TypingIndicator is shown between RUN_STARTED and the first TEXT_MESSAGE_CONTENT.
// Server-authored stage labels and runtime tool names stay authoritative; only
// frontend fallback chrome is localized.

"use client";

import { BrandAvatar } from "@/components/chat/BrandAvatar";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface TypingIndicatorProps {
  /** Server-authored stage label; never retranslated by the frontend. */
  stageLabel?: string | null;
  activeToolName?: string | null;
}

export function TypingIndicator({ stageLabel, activeToolName }: TypingIndicatorProps) {
  const { locale } = useI18n();
  const labelText = stageLabel ?? null;
  const toolText = !labelText && activeToolName ? activeToolName : null;

  return (
    <div className="flex items-start gap-3 py-1">
      <BrandAvatar />
      <div className="flex items-center gap-2 rounded-[2px_8px_8px_8px] border border-border bg-[hsl(0,0%,98%)] px-3 py-2.5">
        {labelText ? (
          <>
            <span className="text-xs text-muted-foreground">{labelText}</span>
            <span className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-pulse" />
          </>
        ) : toolText ? (
          <>
            <span className="text-xs text-muted-foreground">
              {translateChat(locale, "typing.using", { tool: toolText })}
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-pulse" />
          </>
        ) : (
          <>
            <span
              className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </>
        )}
      </div>
    </div>
  );
}
