"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { sessionHref } from "@/lib/sessionHref";

function RecentList() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const pathname = usePathname();
  const { sessions, isLoading, error, refetch } = useSkillSessions(null);
  return <section className="console-nav-group" aria-label={zh ? "最近会话" : "Recent conversations"}>
    <div className="flex items-center justify-between gap-2 px-2">
      <h2 className="console-nav-label">{zh ? "最近会话" : "Recent conversations"}</h2>
      <Link href="/sessions" aria-current={pathname === "/sessions" ? "page" : undefined} className="flex min-h-11 items-center text-xs text-primary">{zh ? "查看全部" : "View all"}</Link>
    </div>
    {isLoading && <p role="status" className="px-3 py-2 text-xs text-muted-foreground">{zh ? "正在读取…" : "Loading…"}</p>}
    {error && <div role="alert" className="px-3 text-xs text-destructive"><p>{zh ? "会话加载失败" : "Could not load conversations"}</p><button type="button" onClick={refetch} className="min-h-11 text-primary">{zh ? "重试" : "Retry"}</button></div>}
    {!isLoading && !error && sessions.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">{zh ? "从一段新对话开始" : "Start a new conversation"}</p>}
    <ul className="space-y-0.5">{sessions.slice(0, 8).map(session => <li key={session.session_id}>
      <Link href={sessionHref(session)} title={session.title || undefined} className="console-nav-item"><span className="truncate">{session.title || (zh ? "未命名对话" : "Untitled conversation")}</span></Link>
    </li>)}</ul>
  </section>;
}

export function RecentConversations() {
  const { user, loading } = useAuth();
  return user && !loading ? <RecentList key={user.uid} /> : null;
}
