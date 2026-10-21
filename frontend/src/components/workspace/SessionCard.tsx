"use client";

import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import type { ChatSessionSummary } from "@/hooks/useSkillSessions";
import { sessionHref } from "@/lib/sessionHref";

export function SessionCard({ session }: { session: ChatSessionSummary }) {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const date = new Date(session.last_message_at);
  return (
    <li className="glass-panel p-5">
      <Link href={sessionHref(session)} className="block space-y-3 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
        <h3 className="break-words text-base font-semibold text-foreground">{session.title || (zh ? "未命名会话" : "Untitled session")}</h3>
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          {session.skill_label && <span className="badge px-2 py-1">{session.skill_label}</span>}
          {!Number.isNaN(date.getTime()) && <time dateTime={session.last_message_at}>{date.toLocaleString(locale)}</time>}
        </div>
        {session.transcript_lost && <p className="text-sm text-muted-foreground">{zh ? "此会话的历史消息已不可用" : "This session’s messages are no longer available"}</p>}
        <span className="inline-block text-sm text-primary">{zh ? "打开会话" : "Open session"} →</span>
      </Link>
    </li>
  );
}
