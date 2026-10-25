"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions, type SessionSearchFilters } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionCard } from "@/components/workspace/SessionCard";
import { TASK_STATUS_LABELS } from "@/components/workspace/TaskStatus";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";

function SessionsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [validation, setValidation] = useState(false);
  const [filters, setFilters] = useState<SessionSearchFilters>({});
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null, filters);
  const searching = Boolean(filters.taskStatus || filters.query || filters.updatedAfter || filters.updatedBefore);
  const apply = (event: FormEvent) => {
    event.preventDefault();
    if (from && to && from > to) { setValidation(true); return; }
    setValidation(false);
    const start = from ? new Date(`${from}T00:00:00`) : null;
    const end = to ? new Date(`${to}T00:00:00`) : null;
    if (end) end.setDate(end.getDate() + 1);
    const next = { taskStatus: status, query: query.trim(), updatedAfter: start?.toISOString(), updatedBefore: end?.toISOString() };
    if ((filters.taskStatus ?? "") === status && (filters.query ?? "") === next.query && (filters.updatedAfter ?? "") === (next.updatedAfter ?? "") && (filters.updatedBefore ?? "") === (next.updatedBefore ?? "")) refetch();
    else setFilters(next);
  };
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      <header className="glass-panel space-y-4 p-6 sm:p-8">
        <p className="text-xs text-muted-foreground">{zh ? "你的工作台" : "Your workspace"}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{zh ? "全部对话" : "Conversations"}</h1>
        <p className="text-sm text-muted-foreground">{zh ? "随时继续讨论，查找历史记录，或开始一段新的对话。" : "Continue a discussion, find your history or start a new conversation."}</p>
        <Link href="/chat/root-agent" className="button-primary inline-flex px-4 py-2">{zh ? "新对话" : "New chat"}</Link>
      </header>
      <form onSubmit={apply} className="glass-panel space-y-4 p-5">
        <div className="space-y-2">
          <label htmlFor="session-search" className="block text-sm font-medium text-foreground">{zh ? "搜索历史会话" : "Search sessions"}</label>
          <input id="session-search" type="search" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "标题或会话编号" : "Title or session ID"} className="w-full min-w-0 rounded-xl border border-border bg-background px-4 py-3 text-foreground" />
          <p className="text-sm text-muted-foreground">{zh ? "搜索当前账号的全部历史会话，结果按最近更新时间排序。" : "Search all your sessions, ordered by last update."}</p>
        </div>
        <details><summary className="flex min-h-11 cursor-pointer items-center text-sm text-muted-foreground">{zh ? "按计划报告筛选" : "Filter by reported plan"}</summary>
        <div className="space-y-2 text-sm"><label htmlFor="session-plan-status" className="block">{zh ? "计划报告状态" : "Reported plan status"}</label><select id="session-plan-status" className="glass-control w-full px-3" value={status} onChange={event => setStatus(event.target.value)}><option value="">{zh ? "全部状态" : "All statuses"}</option>{Object.entries(TASK_STATUS_LABELS).map(([key, labels]) => <option key={key} value={key}>{labels[zh ? 0 : 1]}</option>)}</select></div>
        <p className="mt-2 text-xs text-muted-foreground">{zh ? "只筛选助手已保存的计划报告，不代表会话正在运行。" : "Filters saved plan reports, not whether a conversation is running."}</p></details>
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          <label className="min-w-0 text-sm">{zh ? "更新时间起" : "Updated from"}<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="mt-1 block min-h-11 w-full min-w-0 rounded-xl border border-border bg-background px-3 text-foreground" /></label>
          <label className="min-w-0 text-sm">{zh ? "更新时间止" : "Updated through"}<input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="mt-1 block min-h-11 w-full min-w-0 rounded-xl border border-border bg-background px-3 text-foreground" /></label>
        </div>
        {validation && <p role="alert" className="text-sm text-destructive">{zh ? "开始日期不能晚于结束日期。" : "Start date must not follow end date."}</p>}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="button-primary min-h-11 px-4 py-2">{zh ? "搜索" : "Search"}</button>
          <button type="button" className="button-ghost min-h-11 px-4 py-2" onClick={() => { setStatus(""); setQuery(""); setFrom(""); setTo(""); setValidation(false); setFilters({}); }}>{zh ? "重置" : "Reset"}</button>
        </div>
      </form>
      <SessionFeedback error={error} isLoading={isLoading} empty={!searching && sessions.length === 0} retry={refetch} />
      {!error && !isLoading && searching && sessions.length === 0 && <p role="status" className="glass-panel p-6 text-sm text-muted-foreground">{zh ? "没有匹配的历史会话，请调整搜索条件。" : "No matching sessions. Try different filters."}</p>}
      <ul aria-label={zh ? "会话搜索结果" : "Session search results"} className="grid gap-4 sm:grid-cols-2">{sessions.map((session) => <SessionCard key={session.session_id} session={session} />)}</ul>
      {nextCursor && <button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-ghost px-4 py-2 disabled:opacity-50">{isLoadingMore ? (zh ? "正在加载更多…" : "Loading more…") : (zh ? "加载更多" : "Load more")}</button>}
    </main>
  );
}

export default function SessionsPage() {
  return <WorkspaceGate content={SessionsContent} />;
}
