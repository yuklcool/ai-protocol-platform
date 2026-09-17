"use client";

import { useEffect, useState } from "react";
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface PinnedWelcomeProps {
  /** Markdown body — typically the skill's `welcome.intro_message` or
   * legacy `initial_message` field. Empty string disables the component. */
  content: string;
  /** Skill id used to scope the collapse-state key so toggling on one
   * skill doesn't affect another. */
  skillId: string;
  /** Optional skill display name surfaced as part of the header label. */
  skillDisplayName?: string;
  /** Custom Skill-authored header label. When present it stays authoritative. */
  headerLabel?: string;
}

const KEY_PREFIX = "aitana.welcome.collapsed:";

export function PinnedWelcome({
  content,
  skillId,
  skillDisplayName,
  headerLabel,
}: PinnedWelcomeProps) {
  const [collapsed, setCollapsed] = useState(false);
  const { locale } = useI18n();

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.sessionStorage.getItem(KEY_PREFIX + skillId);
    if (stored === "1") setCollapsed(true);
  }, [skillId]);

  if (!content) return null;

  const toggle = () => {
    setCollapsed((v) => {
      const next = !v;
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(KEY_PREFIX + skillId, next ? "1" : "0");
      }
      return next;
    });
  };

  const label =
    headerLabel ??
    (skillDisplayName
      ? translateChat(locale, "welcome.getStartedWith", { skill: skillDisplayName })
      : translateChat(locale, "welcome.getStarted"));

  return (
    <div className="border-b bg-muted/30">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-2 px-4 py-2 text-left text-xs font-medium text-muted-foreground hover:bg-muted"
        aria-expanded={!collapsed}
        aria-controls="pinned-welcome-body"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={collapsed ? "" : "rotate-90"}
          aria-hidden="true"
        >
          <polyline points="4 2 8 6 4 10" />
        </svg>
        <span>{label}</span>
      </button>
      {!collapsed && (
        <div id="pinned-welcome-body" className="px-4 pb-4 text-sm text-foreground">
          <ChatMarkdown content={content} navigateToBlock={() => {}} />
        </div>
      )}
    </div>
  );
}
