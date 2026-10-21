"use client";

import { useState } from "react";
import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionCard } from "@/components/workspace/SessionCard";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";

function SessionsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null);
  const [query, setQuery] = useState("");
  const search = query.trim().toLocaleLowerCase();
  const filtered = sessions.filter((session) => [session.title, session.skill_label, session.session_id].some((value) => value?.toLocaleLowerCase().includes(search)));
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      <header className="glass-panel space-y-4 p-6 sm:p-8">
        <Link href="/workspace" className="text-sm text-primary">{zh ? "返回工作台" : "Back to workspace"}</Link>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{zh ? "全部会话" : "All sessions"}</h1>
        <Link href="/chat/root-agent" className="button-primary inline-flex px-4 py-2">{zh ? "开始任务" : "Start a task"}</Link>
      </header>
      <div className="space-y-2">
        <label htmlFor="session-search" className="block text-sm font-medium text-foreground">{zh ? "搜索已加载会话" : "Search loaded sessions"}</label>
        <input id="session-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-xl border border-border bg-background px-4 py-3 text-foreground" />
        <p className="text-sm text-muted-foreground">{zh ? "仅搜索已加载的会话，可加载更多后继续搜索。" : "Search covers loaded sessions only. Load more to search further."}</p>
      </div>
      <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
      {!error && !isLoading && sessions.length > 0 && filtered.length === 0 && <p className="text-sm text-muted-foreground">{zh ? "已加载会话中没有匹配项。" : "No matches in loaded sessions."}</p>}
      <ul className="grid gap-4 sm:grid-cols-2">{filtered.map((session) => <SessionCard key={session.session_id} session={session} />)}</ul>
      {nextCursor && <button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-ghost px-4 py-2 disabled:opacity-50">{isLoadingMore ? (zh ? "正在加载更多…" : "Loading more…") : (zh ? "加载更多" : "Load more")}</button>}
    </main>
  );
}

export default function SessionsPage() {
  return <WorkspaceGate content={SessionsContent} />;
}
