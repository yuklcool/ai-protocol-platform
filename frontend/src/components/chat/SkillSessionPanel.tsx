"use client";

import type { ChatSessionSummary } from "@/hooks/useSkillSessions";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";
import type { Locale } from "@/lib/i18n";

interface SkillSessionPanelProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  isLoading: boolean;
  error?: string | null;
  onRetry?: () => void;
  nextCursor?: string | null;
  onLoadMore?: () => void;
  isLoadingMore?: boolean;
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
  error = null,
  onRetry,
  nextCursor = null,
  onLoadMore,
  isLoadingMore = false,
  onSelectSession,
  onDelete,
  skillFilter = null,
  onFilterChange,
}: SkillSessionPanelProps) {
  const { locale } = useI18n();
  const options = agentOptions(sessions);
  const showFilter = Boolean(onFilterChange) && (options.length > 1 || skillFilter !== null);

  const filterRow = showFilter ? (
    <div className="shrink-0 px-3 pb-3">
      <select
        aria-label={translateChat(locale, "sessions.filterAria")}
        value={skillFilter ?? ""}
        onChange={(e) => onFilterChange?.(e.target.value || null)}
        className="min-h-10 w-full rounded-lg border bg-background px-3 py-2 text-xs text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {filterRow}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-3" data-resource-scroll="history">
      {isLoading && sessions.length === 0 && <SessionSkeleton locale={locale} />}
      {error && (
        <div role="alert" className="space-y-2 p-3 text-xs text-destructive">
          <p>{translateChat(locale, "sessions.loadFailed")}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={isLoading || isLoadingMore}
              className="button-secondary px-3 py-1.5 text-xs focus-visible:ring-2 focus-visible:ring-primary"
            >
              {translateChat(locale, "shell.retry")}
            </button>
          )}
        </div>
      )}
      {!error && !isLoading && sessions.length === 0 && (
        <div className="p-3 text-xs text-muted-foreground">
          {translateChat(locale, skillFilter ? "sessions.noneForAgent" : "sessions.none")}
        </div>
      )}
      {isLoading && sessions.length > 0 && <p role="status" className="p-2 text-xs text-muted-foreground">{translateChat(locale, "sessions.loadingAria")}</p>}
      <nav aria-label={translateChat(locale, "sessions.historyAria")} aria-busy={isLoading || isLoadingMore} className="flex flex-col gap-1">
        {sessions.map((s) => {
          const isActive = s.session_id === activeSessionId;
          const title =
            s.title ?? translateChat(locale, "sessions.fallbackTitle", { id: s.session_id.slice(0, 8) });
          return (
            <div
              key={s.session_id}
              className={[
                "group flex w-full items-center gap-1 rounded-xl px-1 transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                isActive ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground",
              ].join(" ")}
            >
              <button
                type="button"
                onClick={() => onSelectSession(s.session_id)}
                className="flex min-h-14 min-w-0 flex-1 flex-col justify-center gap-1 px-2 py-2 text-left focus-visible:rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                aria-current={isActive ? "true" : undefined}
                title={title}
              >
                  <span className="w-full truncate text-[13px] font-medium text-foreground">{title}</span>
                <span className="flex w-full min-w-0 items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  {s.transcript_lost ? (
                    <span
                      data-testid="session-transcript-lost"
                      className="truncate text-amber-600"
                      title={translateChat(locale, "sessions.transcriptLostTitle")}
                    >
                      {translateChat(locale, "sessions.messagesUnavailable")}
                    </span>
                  ) : (
                    <span
                      data-testid={s.skill_label ? "session-agent-label" : undefined}
                      className="truncate"
                    >
                      {s.skill_label || ""}
                    </span>
                  )}
                <span className="shrink-0">
                  {relativeTime(s.last_message_at, locale)}
                </span>
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
                  className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground opacity-100 hover:bg-destructive/10 hover:text-destructive focus-visible:ring-2 focus-visible:ring-primary md:min-h-8 md:min-w-8 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
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
      {nextCursor && onLoadMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={isLoading || isLoadingMore}
          className="button-secondary m-2 px-3 py-1.5 text-xs focus-visible:ring-2 focus-visible:ring-primary"
        >
          {translateChat(locale, isLoadingMore ? "sessions.loadingMore" : "sessions.loadMore")}
        </button>
      )}
      {isLoadingMore && <p role="status" className="px-2 text-xs text-muted-foreground">{translateChat(locale, "sessions.loadingMore")}</p>}
      </div>
    </div>
  );
}
