"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions, type ChatSessionSummary } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";
import { fetchWithAuth } from "@/lib/apiClient";
import { ReportEditor, type SavedReport } from "@/components/chat/ReportEditor";
import { sessionHref } from "@/lib/sessionHref";

type SessionResult = {
  surface_id: string;
  title: string;
  kind: string | null;
  description: string | null;
  created_at: number | null;
};
type SessionResults = {
  session_id: string;
  results: SessionResult[];
  state_available: boolean;
  incomplete_count: number;
  truncated: boolean;
};

function isResults(value: unknown, sessionId: string): value is SessionResults {
  if (!value || typeof value !== "object") return false;
  const body = value as SessionResults;
  return body.session_id === sessionId && typeof body.state_available === "boolean"
    && Number.isInteger(body.incomplete_count) && body.incomplete_count >= 0
    && typeof body.truncated === "boolean" && Array.isArray(body.results)
    && body.results.every((item) => item && typeof item.surface_id === "string"
      && typeof item.title === "string" && (item.kind === null || typeof item.kind === "string")
      && (item.description === null || typeof item.description === "string")
      && (item.created_at === null || (typeof item.created_at === "number" && Number.isFinite(item.created_at))));
}

function ResultsDetails({ session }: { session: ChatSessionSummary }) {
  const { locale } = useI18n();
  const headingId = useId();
  const zh = locale.startsWith("zh");
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [data, setData] = useState<SessionResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<number | "network" | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setData(null);
    setReports([]);
    setError(null);
    void (async () => {
      try {
        const response = await fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(session.session_id)}/results`, { signal: controller.signal });
        if (!response.ok) {
          if (!controller.signal.aborted) setError(response.status);
          return;
        }
        const body: unknown = await response.json();
        if (!isResults(body, session.session_id)) throw new Error("Invalid results response");
        const reportsResponse = await fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(session.session_id)}/reports`, { signal: controller.signal });
        if (!reportsResponse.ok) throw new Error("Reports unavailable");
        const saved = await reportsResponse.json() as { reports: SavedReport[] };
        if (!controller.signal.aborted) { setData(body); setReports(saved.reports); }
      } catch {
        if (!controller.signal.aborted) setError("network");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [session.session_id, revision]);
  const title = session.title || (zh ? "未命名会话" : "Untitled session");
  return (
    <section aria-labelledby={headingId} aria-busy={loading} className="glass-panel min-w-0 space-y-4 p-5 sm:p-6">
      <header className="space-y-2">
        <h2 id={headingId} className="break-words text-xl font-semibold">{title}</h2>

        <div className="flex flex-wrap gap-3">
          <Link href={sessionHref(session)} className="button-primary inline-flex items-center px-4 py-2">{zh ? "返回原对话" : "Return to conversation"}</Link>
          <button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)} className="button-secondary px-4 py-2 disabled:opacity-50">{zh ? "刷新成果" : "Refresh results"}</button>
        </div>
      </header>
      {session.transcript_lost && <p className="notice notice--warning text-sm">{zh ? "此会话的历史消息可能已不可用，返回对话不保证能恢复成果正文。" : "This session's transcript may be unavailable; returning may not restore result content."}</p>}
      {loading && <p role="status" className="text-sm text-muted-foreground">{zh ? "正在读取成果摘要…" : "Loading result summaries…"}</p>}
      {error && <div role="alert" className="notice notice--danger space-y-2 text-sm">
        <p>{error === 401 || error === 403
          ? zh ? "没有权限读取此会话成果，请核对登录账号与授权。" : "You cannot access these results. Check your account and permissions."
          : error === 404
            ? zh ? "此会话已不存在或无法访问。" : "This session no longer exists or is inaccessible."
            : zh ? "成果读取失败，不代表此会话没有成果。" : "Could not load results. This does not mean there are none."}</p>
        <button type="button" onClick={() => setRevision((value) => value + 1)} className="button-secondary px-3 py-2">{zh ? "重试成果读取" : "Retry results"}</button>
      </div>}
      {!loading && data && <div className="space-y-4" aria-live="polite">
        {!data.state_available && <p role="status" className="notice notice--warning text-sm">{zh ? "会话成果状态不可用，不能据此判断没有成果。可返回原对话核对。" : "Result state is unavailable; this is not proof of no results. Check the original conversation."}</p>}
        {data.incomplete_count > 0 && <p role="status" className="notice notice--warning text-sm">{zh ? `有 ${data.incomplete_count} 条状态不完整，部分成果可能缺失或摘要已降级。` : `${data.incomplete_count} state entries are incomplete; results may be missing or summaries degraded.`}</p>}
        {data.truncated && <p role="status" className="notice notice--warning text-sm">{zh ? "仅显示前 100 个成果，列表已截断；请返回原对话核对其余内容。" : "Only the first 100 results are shown. Return to the conversation to check the rest."}</p>}
        {data.state_available && data.results.length === 0 && reports.length === 0 && <p className="text-sm text-muted-foreground">{zh ? "未找到可展示的持久化交互成果摘要。上传附件、知识来源和普通聊天文本不计入此列表。" : "No persisted interactive-result summaries were found. Uploads, knowledge sources and ordinary chat text are not listed as results."}</p>}
        {reports.map(report => <article key={report.report_id} className="surface-sunken space-y-3 p-4"><span className="badge badge--brand">TXT · v{report.revision}</span><h3>{report.title}</h3><p className="line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{report.content}</p><time className="block text-xs text-muted-foreground" dateTime={report.updated_at}>{new Date(report.updated_at).toLocaleString(locale)}</time><ReportEditor sessionId={session.session_id} messageId={report.message_id} content={report.content} initialReport={report} /></article>)}
        <ul className="space-y-3">{data.results.map((result) => {
          const date = result.created_at === null ? null : new Date(result.created_at);
          const validDate = date && Number.isFinite(date.getTime()) ? date : null;
          return <li key={`${session.session_id}:${result.surface_id}`} className="surface-sunken space-y-2 p-4">
            <h3 className="break-words font-medium">{result.title}</h3>
            {result.kind && <p className="text-xs text-muted-foreground">{result.kind}</p>}
            {result.description && <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{result.description}</p>}
            {validDate && <time dateTime={validDate.toISOString()} className="block text-xs text-muted-foreground">{validDate.toLocaleString(zh ? "zh-CN" : "en-US")}</time>}
            <p className="break-all text-xs text-muted-foreground">Surface: {result.surface_id}</p>
          </li>;
        })}</ul>
      </div>}
    </section>
  );
}

function ResultsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null, { query: search });
  return (
    <main className="page-container mx-auto max-w-6xl">
      <header className="page-header"><div><p className="page-header__eyebrow">{zh ? "从对话到交付" : "From conversation to delivery"}</p><h1 className="page-header__title">{zh ? "我的成果" : "My results"}</h1><p className="page-header__desc">{zh ? "报告与交互成果按来源会话归档。编辑、保存、下载，或返回对话继续完善。" : "Reports and interactive results, grouped by source conversation. Edit, save, download or continue in chat."}</p></div><Link href="/chat/root-agent" className="button-primary">{zh ? "创建新成果" : "Create a result"}</Link></header>
      <form className="results-search glass-panel flex flex-wrap items-end gap-3 p-4" onSubmit={event => { event.preventDefault(); if (search === query.trim()) refetch(); else setSearch(query.trim()); }}><label className="min-w-0 flex-1 space-y-2 text-sm" htmlFor="result-session-search"><span>{zh ? "搜索来源会话" : "Search source conversations"}</span><input id="result-session-search" type="search" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder={zh ? "搜索全部历史会话标题或编号" : "Search all session titles or IDs"} className="glass-control w-full px-3" /></label><button type="submit" className="button-secondary">{zh ? "搜索" : "Search"}</button></form>
      <p className="my-4 text-xs text-muted-foreground">{zh ? "每页读取 20 个会话的已保存成果；搜索覆盖全部历史会话，正文不参与搜索。上传附件不计为成果。" : "Saved results from 20 sessions per page. Search covers all session titles and IDs, not result content. Uploads are not results."}</p>
      <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
      <div className="grid items-start gap-5 lg:grid-cols-2">{sessions.map(session => <ResultsDetails key={session.session_id} session={session} />)}</div>
      {nextCursor && <button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-secondary mt-6">{isLoadingMore ? (zh ? "正在加载…" : "Loading…") : (zh ? "加载更多成果" : "Load more results")}</button>}
    </main>
  );
}

export default function ResultsPage() {
  return <WorkspaceGate content={ResultsContent} />;
}
