"use client";

import Link from "next/link";
import { useState } from "react";
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
    <li className="glass-panel session-card p-5">
      <Link href={sessionHref(session)} className="block space-y-3 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
        <h3 className="break-words text-base font-semibold text-foreground">{session.title || (zh ? "未命名会话" : "Untitled session")}</h3>
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          {session.skill_label && <span className="badge px-2 py-1">{session.skill_label}</span>}
          {!Number.isNaN(date.getTime()) && <time dateTime={session.last_message_at}>{date.toLocaleString(locale)}</time>}
        </div>
        {session.transcript_lost && <p className="text-sm text-muted-foreground">{zh ? "此会话的历史消息已不可用" : "This session’s messages are no longer available"}</p>}
        <span className="inline-block text-sm text-primary">{zh ? "打开会话" : "Open session"} →</span>
      </Link>
      {session.task_status && session.task_status !== "unplanned" && <details className="mt-3 border-t pt-2 text-sm">
        <summary className="flex min-h-11 cursor-pointer items-center text-muted-foreground">{zh ? "最近的计划报告" : "Latest reported plan"}</summary>
        <div className="space-y-2 pb-3"><TaskStatus status={session.task_status} />{session.task_title && <p>{session.task_title}</p>}{session.task_progress && <p>{session.task_progress.completed}/{session.task_progress.total}</p>}<p className="text-xs text-muted-foreground">{zh ? "仅表示最近一次计划报告，不代表整段对话或后台运行状态。" : "This describes the latest plan report, not the conversation or a background worker."}</p></div>
      </details>}
      {session.is_owner && <button type="button" disabled={archiving} onClick={() => void archive()} className="button-ghost mt-2 min-h-11 text-xs">{archiving ? (zh ? "正在归档…" : "Archiving…") : (zh ? "归档会话" : "Archive conversation")}</button>}
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{zh ? "归档失败，会话仍保留，请重试。" : "Archive failed. The conversation is kept. Please retry."}</p>}
    </li>
  );
}
