"use client";

import type { ChatSessionSummary } from "@/hooks/useSkillSessions";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";
import type { Locale } from "@/lib/i18n";

interface SkillSessionPanelProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  isLoading: boolean;
  onSelectSession: (sessionId: string) => void;
  onDelete?: (sessionId: string) => void;
  skillFilter?: string | null;
  onFilterChange?: (skillId: string | null) => void;
}

function SessionSkeleton({ locale }: { locale: Locale }) {
  return (
    <div className="space-y-1 p-1" aria-label={translateChat(locale, "sessions.loadingAria")}>
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-7 animate-pulse rounded bg-muted" />
      ))}
    </div>
  );
}

function relativeTime(iso: string, locale: Locale): string {
  try {
    const diffMs = Date.now() - new Date(iso).getTime();
    const diffMin = Math.floor(diffMs / 60_000);
    if (diffMin < 1) return translateChat(locale, "time.justNow");
    if (diffMin < 60) return translateChat(locale, "time.minutesAgo", { count: diffMin });
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return translateChat(locale, "time.hoursAgo", { count: diffH });
    return translateChat(locale, "time.daysAgo", { count: Math.floor(diffH / 24) });
  } catch {
    return "";
  }
}

function agentOptions(sessions: ChatSessionSummary[]): Array<{ id: string; label: string }> {
  const seen = new Map<string, string>();
  for (const s of sessions) {
    if (s.skill_label && !seen.has(s.skill_id)) seen.set(s.skill_id, s.skill_label);
  }
  return [...seen.entries()]
    .map(([id, label]) => ({ id, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function SkillSessionPanel({
  sessions,
  activeSessionId,
  isLoading,
  onSelectSession,
  onDelete,
  skillFilter = null,
  onFilterChange,
}: SkillSessionPanelProps) {
  const { locale } = useI18n();
  const options = agentOptions(sessions);
  const showFilter = Boolean(onFilterChange) && (options.length > 1 || skillFilter !== null);

  const filterRow = showFilter ? (
    <div className="px-2 pb-1 pt-0.5">
      <select
        aria-label={translateChat(locale, "sessions.filterAria")}
        value={skillFilter ?? ""}
        onChange={(e) => onFilterChange?.(e.target.value || null)}
        className="w-full rounded border bg-transparent px-1 py-0.5 text-[11px] text-muted-foreground"
      >
        <option value="">{translateChat(locale, "sessions.allAgents")}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
        {skillFilter && !options.some((o) => o.id === skillFilter) && (
          <option value={skillFilter}>{translateChat(locale, "sessions.selectedAgent")}</option>
        )}
      </select>
    </div>
  ) : null;

  if (isLoading) {
    return (
      <>
        {filterRow}
        <SessionSkeleton locale={locale} />
      </>
    );
  }

  if (sessions.length === 0) {
    return (
      <>
        {filterRow}
        <div className="p-3 text-xs text-muted-foreground">
          {translateChat(locale, skillFilter ? "sessions.noneForAgent" : "sessions.none")}
        </div>
      </>
    );
  }

  return (
    <>
      {filterRow}
      <nav aria-label={translateChat(locale, "sessions.historyAria")} className="flex flex-col p-1">
        {sessions.map((s) => {
          const isActive = s.session_id === activeSessionId;
          const title =
            s.title ?? translateChat(locale, "sessions.fallbackTitle", { id: s.session_id.slice(0, 8) });
          return (
            <div
              key={s.session_id}
              className={[
                "group flex w-full items-center gap-1 rounded px-1 transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                isActive ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground",
              ].join(" ")}
            >
              <button
                type="button"
                onClick={() => onSelectSession(s.session_id)}
                className="flex min-w-0 flex-1 items-baseline justify-between gap-2 px-1.5 py-1 text-left"
                aria-current={isActive ? "true" : undefined}
                title={title}
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="line-clamp-1 text-xs">{title}</span>
                  {s.transcript_lost ? (
                    <span
                      data-testid="session-transcript-lost"
                      className="line-clamp-1 text-[10px] text-amber-600 dark:text-amber-500"
                      title={translateChat(locale, "sessions.transcriptLostTitle")}
                    >
                      {translateChat(locale, "sessions.messagesUnavailable")}
                    </span>
                  ) : (
                    s.skill_label && (
                      <span
                        data-testid="session-agent-label"
                        className="line-clamp-1 text-[10px] opacity-60"
                      >
                        {s.skill_label}
                      </span>
                    )
                  )}
                </span>
                <span className="shrink-0 text-[10px] opacity-60">
                  {relativeTime(s.last_message_at, locale)}
                </span>
              </button>
              {onDelete && s.is_owner && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.session_id);
                  }}
                  aria-label={translateChat(locale, "sessions.deleteAria", { title })}
                  title={translateChat(locale, "sessions.delete")}
                  className="shrink-0 rounded p-1 text-gray-400 opacity-0 hover:bg-red-100 hover:text-red-600 group-hover:opacity-100"
                >
                  <svg
                    className="h-3.5 w-3.5"
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 4h10M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4M7 4V3a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v1"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              )}
            </div>
          );
        })}
      </nav>
    </>
  );
}
