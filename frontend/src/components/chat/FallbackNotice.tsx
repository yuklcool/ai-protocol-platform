// MODEL-RELIABILITY M3 — persistent inline notice that a backup model answered.
// Degradation remains explicit; model ids stay verbatim technical identifiers.

"use client";

import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

function displayName(model: string): string {
  return model.includes("/") ? model.split("/").pop()! : model;
}

interface FallbackNoticeProps {
  fromModel: string;
  toModel: string;
  /** "provider_cooldown" = primary skipped (known-bad), not tried-and-failed. */
  reason?: string;
}

export function FallbackNotice({ fromModel, toModel, reason }: FallbackNoticeProps) {
  const { locale } = useI18n();
  const from = displayName(fromModel);
  const to = displayName(toModel);
  const verb = translateChat(
    locale,
    reason === "provider_cooldown" ? "fallback.cooldownVerb" : "fallback.failedVerb",
  );

  return (
    <div
      className="flex items-center gap-2 py-0.5 text-xs text-muted-foreground"
      role="note"
      aria-label={translateChat(locale, "fallback.aria", { from, to })}
      title={`${fromModel} → ${toModel}${reason ? ` (${reason})` : ""}`}
    >
      <span className="ml-10 flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2 py-0.5">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="text-amber-500/70"
        >
          <path d="m18 14 4 4-4 4" />
          <path d="m18 2 4 4-4 4" />
          <path d="M2 18h1.973a4 4 0 0 0 3.3-1.7l5.454-8.6a4 4 0 0 1 3.3-1.7H22" />
          <path d="M2 6h1.972a4 4 0 0 1 3.6 2.2" />
          <path d="M22 18h-6.041a4 4 0 0 1-3.3-1.8l-.359-.45" />
        </svg>
        <span>
          <span className="font-medium text-foreground/70">{from}</span> {verb}{" "}
          <span className="font-medium text-foreground/70">{to}</span>
        </span>
      </span>
    </div>
  );
}
