"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface ThinkingPanelProps {
  content: string;
  isThinking: boolean;
}

export function ThinkingPanel({ content, isThinking }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const { locale } = useI18n();

  // Auto-collapse when thinking finishes
  useEffect(() => {
    if (!isThinking) setExpanded(false);
  }, [isThinking]);

  return (
    <div className="mb-2 rounded border border-primary/20 bg-primary/5 text-xs">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left text-primary"
      >
        {isThinking && (
          <svg
            className="h-3 w-3 animate-spin shrink-0"
            viewBox="0 0 24 24"
            fill="none"
            aria-label={translateChat(locale, "thinking.aria")}
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        <span className="font-medium">
          {isThinking
            ? translateChat(locale, "thinking.active")
            : translateChat(locale, "thinking.process")}
        </span>
        <svg
          className={`ml-auto h-3 w-3 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {expanded && (
        <p className="whitespace-pre-wrap px-2 pb-2 text-muted-foreground">{content}</p>
      )}
    </div>
  );
}
