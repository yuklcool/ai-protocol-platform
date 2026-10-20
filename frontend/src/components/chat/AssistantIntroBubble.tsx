"use client";

import { BrandAvatar } from "@/components/chat/BrandAvatar";
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface AssistantIntroBubbleProps {
  content: string;
  skillName?: string;
}

export function AssistantIntroBubble({ content, skillName }: AssistantIntroBubbleProps) {
  const { locale } = useI18n();

  return (
    <div
      className="flex w-full gap-3"
      role="group"
      aria-label={translateChat(locale, "intro.aria")}
    >
      <BrandAvatar />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-sm font-semibold text-foreground">
            {skillName ?? translateChat(locale, "intro.assistant")}
          </span>
          <span
            className="badge px-2 py-0.5 text-[11px] text-muted-foreground"
            aria-label={translateChat(locale, "intro.notStoredAria")}
          >
            {translateChat(locale, "intro.notStored")}
          </span>
        </div>
        <div className="surface-sunken rounded-2xl px-4 py-3 text-sm leading-relaxed text-foreground">
          <ChatMarkdown content={content} navigateToBlock={() => {}} />
        </div>
      </div>
    </div>
  );
}
