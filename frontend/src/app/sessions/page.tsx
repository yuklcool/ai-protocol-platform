"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Plus, RotateCcw, Search, SlidersHorizontal } from "lucide-react";
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
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterButton = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [filters, setFilters] = useState<SessionSearchFilters>({});
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null, filters);
  const searching = Boolean(filters.taskStatus || filters.query || filters.updatedAfter || filters.updatedBefore);
  const advancedFilterCount = [filters.taskStatus, filters.updatedAfter, filters.updatedBefore].filter(Boolean).length;
  const canReset = searching || Boolean(query || status || from || to);
  const dateLabel = (value: string, exclusive = false) => {
    const date = new Date(value);
    if (exclusive) date.setDate(date.getDate() - 1);
    return date.toLocaleDateString(locale);
  };
  const apply = (event: FormEvent) => {
    event.preventDefault();
    if (from && to && from > to) { setValidation(true); setFiltersOpen(true); return; }
    setValidation(false);
    const start = from ? new Date(`${from}T00:00:00`) : null;
    const end = to ? new Date(`${to}T00:00:00`) : null;
    if (end) end.setDate(end.getDate() + 1);
    const next = { taskStatus: status, query: query.trim(), updatedAfter: start?.toISOString(), updatedBefore: end?.toISOString() };
    if ((filters.taskStatus ?? "") === status && (filters.query ?? "") === next.query && (filters.updatedAfter ?? "") === (next.updatedAfter ?? "") && (filters.updatedBefore ?? "") === (next.updatedBefore ?? "")) refetch();
    else setFilters(next);
    if (filtersOpen) filterButton.current?.focus();
    setFiltersOpen(false);
  };
  return (
    <main className="page-container mx-auto max-w-6xl">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{zh ? "全部对话" : "Conversations"}</h1>
        <Link href="/chat/root-agent" className="button-primary shrink-0 text-sm"><Plus className="h-4 w-4" aria-hidden="true" />{zh ? "新对话" : "New chat"}</Link>
      </header>
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <form onSubmit={apply} className="border-b border-border p-3 sm:p-4">
          <div className="flex min-w-0 items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <label htmlFor="session-search" className="sr-only">{zh ? "搜索历史会话" : "Search sessions"}</label>
              <input ref={searchInput} id="session-search" type="search" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索对话标题或编号" : "Search by title or session ID"} className="glass-control w-full min-w-0 py-2 pl-3 pr-12 text-sm" />
              <button type="submit" aria-label={zh ? "搜索" : "Search"} title={zh ? "搜索" : "Search"} className="button-ghost absolute inset-y-0 right-0 w-11"><Search className="h-4 w-4" aria-hidden="true" /></button>
            </div>
            <button ref={filterButton} type="button" aria-expanded={filtersOpen} aria-controls="session-filters" aria-label={zh ? "筛选" : "Filters"} onClick={() => setFiltersOpen(!filtersOpen)} className={`button-secondary shrink-0 text-sm ${filtersOpen || advancedFilterCount ? "border-primary text-primary" : ""}`}>
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />{zh ? "筛选" : "Filters"}
              {advancedFilterCount > 0 && <span className="rounded bg-primary/10 px-1.5 text-xs">{advancedFilterCount}</span>}
            </button>
            {canReset && <button type="button" aria-label={zh ? "重置" : "Reset"} title={zh ? "重置" : "Reset"} className="button-ghost w-11 shrink-0" onClick={() => { setStatus(""); setQuery(""); setFrom(""); setTo(""); setValidation(false); setFilters({}); searchInput.current?.focus(); }}><RotateCcw className="h-4 w-4" aria-hidden="true" /></button>}
          </div>
          {filtersOpen && <div id="session-filters" className="mt-3 space-y-3 border-t border-border pt-3">
            <div className="grid min-w-0 gap-3 sm:grid-cols-3">
              <label className="min-w-0 space-y-1 text-sm"><span className="block">{zh ? "更新时间起" : "Updated from"}</span><input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="glass-control block w-full min-w-0 px-3" /></label>
              <label className="min-w-0 space-y-1 text-sm"><span className="block">{zh ? "更新时间止" : "Updated through"}</span><input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="glass-control block w-full min-w-0 px-3" /></label>
              <div className="min-w-0 space-y-1 text-sm"><label htmlFor="session-plan-status" className="block">{zh ? "计划报告状态" : "Reported plan status"}</label><select id="session-plan-status" className="glass-control w-full px-3 text-base sm:text-sm" value={status} onChange={event => setStatus(event.target.value)}><option value="">{zh ? "全部状态" : "All statuses"}</option>{Object.entries(TASK_STATUS_LABELS).map(([key, labels]) => <option key={key} value={key}>{labels[zh ? 0 : 1]}</option>)}</select></div>
            </div>
            {validation && <p role="alert" className="text-sm text-destructive">{zh ? "开始日期不能晚于结束日期。" : "Start date must not follow end date."}</p>}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="max-w-prose text-xs text-muted-foreground">{zh ? "计划状态来自助手保存的报告，不代表会话正在运行。" : "Plan status comes from saved reports, not whether a conversation is running."}</p>
              <button type="submit" className="button-secondary text-sm">{zh ? "应用筛选" : "Apply filters"}</button>
            </div>
          </div>}
          {advancedFilterCount > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {filters.taskStatus && <span>{zh ? "计划：" : "Plan: "}{TASK_STATUS_LABELS[filters.taskStatus]?.[zh ? 0 : 1]}</span>}
            {filters.updatedAfter && <span>{zh ? "起：" : "From: "}{dateLabel(filters.updatedAfter)}</span>}
            {filters.updatedBefore && <span>{zh ? "止：" : "Through: "}{dateLabel(filters.updatedBefore, true)}</span>}
          </div>}
        </form>
        {(error || isLoading || sessions.length === 0) && <div className="p-4">
          <SessionFeedback error={error} isLoading={isLoading} empty={!searching && sessions.length === 0} retry={refetch} />
          {!error && !isLoading && searching && sessions.length === 0 && <p role="status" className="py-4 text-sm text-muted-foreground">{zh ? "没有匹配的历史会话，请调整搜索条件。" : "No matching sessions. Try different filters."}</p>}
        </div>}
        {sessions.length > 0 && <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2 text-xs text-muted-foreground"><span>{zh ? "最近更新" : "Recently updated"}</span><span>{zh ? `已显示 ${sessions.length} 段对话` : `${sessions.length} conversations shown`}</span></div>}
        <ul aria-label={zh ? "会话搜索结果" : "Session search results"} className="divide-y divide-border">{sessions.map((session) => <SessionCard key={session.session_id} session={session} />)}</ul>
        {nextCursor && <div className="border-t border-border p-2 text-center"><button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-ghost w-full text-sm disabled:opacity-50">{isLoadingMore ? (zh ? "正在加载更多…" : "Loading more…") : (zh ? "加载更多" : "Load more")}</button></div>}
      </div>
    </main>
  );
}

export default function SessionsPage() {
  return <WorkspaceGate content={SessionsContent} />;
}
