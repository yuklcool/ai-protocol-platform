"use client";

import Link from "next/link";
import { useState } from "react";
import { Archive, ChevronDown, MessageSquare } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import type { ChatSessionSummary } from "@/hooks/useSkillSessions";
import { TaskStatus } from "./TaskStatus";
import { sessionHref } from "@/lib/sessionHref";
import { fetchWithAuth } from "@/lib/apiClient";
import { notifySessionsChanged } from "@/lib/sessionEvents";

export function SessionCard({ session }: { session: ChatSessionSummary }) {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const date = new Date(session.last_message_at);
  const title = session.title || (zh ? "未命名会话" : "Untitled session");
  const [archiving, setArchiving] = useState(false);
  const [error, setError] = useState(false);
  async function archive() {
    if (archiving || !window.confirm(zh ? "归档这段会话？归档后将从会话列表移除，已保存的记录仍会保留。" : "Archive this conversation? It will leave the list; saved records are retained.")) return;
    setArchiving(true);
    setError(false);
    try {
      const response = await fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(session.session_id)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      notifySessionsChanged({ deletedSessionId: session.session_id });
    } catch { setError(true); }
    finally { setArchiving(false); }
  }
  return (
    <li className="px-3 transition-colors hover:bg-muted/40 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <Link href={sessionHref(session)} className="flex min-h-16 min-w-0 flex-1 items-center gap-3 rounded-lg py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
          <MessageSquare className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" aria-hidden="true" />
          <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <div className="min-w-0 space-y-1">
              <h2 title={title} className="line-clamp-2 break-words text-sm font-medium text-foreground sm:line-clamp-1">{title}</h2>
              {session.transcript_lost && <p className="text-xs text-muted-foreground">{zh ? "此会话的历史消息已不可用" : "This session’s messages are no longer available"}</p>}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {session.skill_label && <span className="max-w-24 truncate" title={session.skill_label}>{session.skill_label}</span>}
              {!Number.isNaN(date.getTime()) && <time dateTime={session.last_message_at} title={date.toLocaleString(locale)} className="tabular-nums">{date.toLocaleString(locale, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>}
            </div>
          </div>
        </Link>
        {session.is_owner && <button type="button" disabled={archiving} onClick={() => void archive()} aria-label={archiving ? (zh ? "正在归档…" : "Archiving…") : (zh ? "归档会话" : "Archive conversation")} title={zh ? "归档会话" : "Archive conversation"} className="button-ghost w-11 shrink-0 disabled:opacity-50"><Archive className="h-4 w-4" aria-hidden="true" /></button>}
      </div>
      {session.task_status && session.task_status !== "unplanned" && <details className="group pb-1 text-sm sm:pl-7">
        <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-1.5 rounded text-xs text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden"><ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />{zh ? "最近的计划报告" : "Latest reported plan"}</summary>
        <div className="space-y-2 pb-3"><TaskStatus status={session.task_status} />{session.task_title && <p>{session.task_title}</p>}{session.task_progress && <p>{session.task_progress.completed}/{session.task_progress.total}</p>}<p className="text-xs text-muted-foreground">{zh ? "仅表示最近一次计划报告，不代表整段对话或后台运行状态。" : "This describes the latest plan report, not the conversation or a background worker."}</p>
        </div>
      </details>}
      {error && <p role="alert" className="pb-3 text-sm text-destructive">{zh ? "归档失败，会话仍保留，请重试。" : "Archive failed. The conversation is kept. Please retry."}</p>}
    </li>
  );
}
