// SKILL-DELEGATION M3 — persistent inline marker for a skill-to-skill handoff.

"use client";

import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface DelegationMarkerProps {
  targetDisplay: string;
  /** "auto" = a completed handoff; "suggest" = a proposed handoff awaiting confirm. */
  mode: "auto" | "suggest";
}

export function DelegationMarker({ targetDisplay, mode }: DelegationMarkerProps) {
  const { locale } = useI18n();
  const prefix = translateChat(
    locale,
    mode === "suggest" ? "delegation.suggested" : "delegation.delegated",
  );
  const aria = translateChat(
    locale,
    mode === "suggest" ? "delegation.suggestAria" : "delegation.delegateAria",
    { target: targetDisplay },
  );

  return (
    <div
      className="flex items-center gap-2 py-0.5 text-xs text-muted-foreground"
      role="note"
      aria-label={aria}
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
          className="text-orange-500/70"
        >
          <path d="M5 12h14" />
          <path d="m13 5 7 7-7 7" />
        </svg>
        <span>
          {prefix}{" "}
          <span className="font-medium text-foreground/70">{targetDisplay}</span>
        </span>
      </span>
    </div>
  );
}
