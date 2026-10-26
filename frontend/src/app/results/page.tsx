"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
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

type ResultStatus = "loading" | "empty" | "review" | "visible";

function ResultsDetails({ session, onStatus, showReview }: { session: ChatSessionSummary; onStatus: (id: string, status: ResultStatus) => void; showReview: boolean }) {
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
  const empty = !loading && !error && data?.state_available === true
    && data.incomplete_count === 0 && !data.truncated
    && data.results.length === 0 && reports.length === 0 && !session.transcript_lost;
  const reviewOnly = !loading && !error && !empty && data !== null && data.results.length === 0 && reports.length === 0;
  useEffect(() => {
    onStatus(session.session_id, loading ? "loading" : empty ? "empty" : reviewOnly ? "review" : "visible");
  }, [session.session_id, loading, empty, reviewOnly, onStatus]);
  const title = session.title || (zh ? "未命名会话" : "Untitled session");
  if (empty || (reviewOnly && !showReview)) return null;
  if (loading) return <p role="status" className="flex items-center gap-3 px-4 py-3 text-sm text-muted-foreground"><span className="skeleton h-4 w-4 shrink-0" aria-hidden="true" /><span className="truncate">{title} · {zh ? "正在读取成果…" : "Loading results…"}</span></p>;
  const Container = reviewOnly ? "details" : "section";
  return (
    <Container aria-labelledby={headingId} className="glass-panel min-w-0">
      {reviewOnly && <summary className="min-h-11 cursor-pointer px-4 py-3 text-sm"><span className="mr-2 break-words">{title}</span><span className="badge badge--warning">{zh ? "成果状态需核对" : "Result state needs review"}</span></summary>}
      <div className="space-y-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <h2 id={headingId} className="min-w-0 break-words text-sm font-semibold">{title}</h2>

        <div className="flex flex-wrap gap-2">
          <Link href={sessionHref(session)} className="button-secondary text-xs">{zh ? "返回原对话" : "Return to conversation"}</Link>
          <button type="button" onClick={() => setRevision((value) => value + 1)} className="button-ghost text-xs">{zh ? "刷新成果" : "Refresh results"}</button>
        </div>
      </header>
      {session.transcript_lost && <p className="notice notice--warning text-sm">{zh ? "此会话的历史消息可能已不可用，返回对话不保证能恢复成果正文。" : "This session's transcript may be unavailable; returning may not restore result content."}</p>}
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
        {reports.map(report => <article key={report.report_id} className="surface-sunken space-y-3 p-4"><span className="badge badge--brand">TXT · v{report.revision}</span><h3>{report.title}</h3><p className="line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{report.content}</p><time className="block text-xs text-muted-foreground" dateTime={report.updated_at}>{new Date(report.updated_at).toLocaleString(locale)}</time><ReportEditor sessionId={session.session_id} messageId={report.message_id} content={report.content} initialReport={report} /></article>)}
        <ul className="space-y-3">{data.results.map((result) => {
          const date = result.created_at === null ? null : new Date(result.created_at);
          const validDate = date && Number.isFinite(date.getTime()) ? date : null;
          return <li key={`${session.session_id}:${result.surface_id}`} className="surface-sunken space-y-2 p-4">
            <h3 className="break-words font-medium">{result.title}</h3>
            {result.kind && <p className="text-xs text-muted-foreground">{result.kind}</p>}
            {result.description && <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{result.description}</p>}
            {validDate && <time dateTime={validDate.toISOString()} className="block text-xs text-muted-foreground">{validDate.toLocaleString(zh ? "zh-CN" : "en-US")}</time>}
            <details className="text-xs text-muted-foreground"><summary className="cursor-pointer py-2">{zh ? "成果详情" : "Result details"}</summary><p className="break-all">Surface: {result.surface_id}</p></details>
          </li>;
        })}</ul>
      </div>}
      </div>
    </Container>
  );
}

function ResultsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [showReview, setShowReview] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, ResultStatus>>({});
  const onStatus = useCallback((id: string, status: ResultStatus) => {
    setStatuses(previous => previous[id] === status ? previous : { ...previous, [id]: status });
  }, []);
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null, { query: search });
  const pageEmpty = sessions.length > 0 && sessions.every(session => statuses[session.session_id] === "empty");
  const reviewCount = sessions.filter(session => statuses[session.session_id] === "review").length;
  const renderResult = (session: ChatSessionSummary) => <ResultsDetails key={`session:${session.session_id}`} session={session} onStatus={onStatus} showReview={showReview} />;
  return (
    <main className="page-container mx-auto max-w-6xl">
      <header className="page-header page-header--compact"><h1 className="page-header__title">{zh ? "我的成果" : "My results"}</h1><Link href="/chat/root-agent" className="button-primary">{zh ? "创建新成果" : "Create a result"}</Link></header>
      <form className="results-search mb-3 flex items-center gap-2" onSubmit={event => { event.preventDefault(); if (search === query.trim()) refetch(); else setSearch(query.trim()); }}><label className="min-w-0 flex-1 text-sm" htmlFor="result-session-search"><span className="sr-only">{zh ? "搜索来源会话" : "Search source conversations"}</span><input id="result-session-search" type="search" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder={zh ? "搜索来源对话标题或编号" : "Search source titles or IDs"} className="glass-control w-full px-3" /></label><button type="submit" className="button-secondary">{zh ? "搜索" : "Search"}</button></form>
      <details className="mb-4 text-xs text-muted-foreground"><summary className="cursor-pointer py-2">{zh ? "成果与搜索范围" : "About results and search"}</summary><p className="pb-2">{zh ? "按来源对话分页查找已保存的报告和交互成果。搜索匹配对话标题与编号，正文不参与；上传附件不计为成果。当前页没有成果时，可继续加载更早的对话。" : "Saved reports and interactive results are grouped by source conversation. Search matches conversation titles and IDs, not content. Uploads are excluded. Load earlier conversations if this page has no results."}</p></details>
      <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
      {!isLoading && pageEmpty && <div role="status" className="empty-state"><h2 className="empty-state__title">{zh ? "已检查的对话中暂无保存成果" : "No saved results in the checked conversations"}</h2><p className="empty-state__desc">{nextCursor ? (zh ? "可继续加载更早的对话，或搜索来源标题。" : "Load earlier conversations or search by source title.") : (zh ? "可在对话中保存报告，之后在这里编辑和下载。" : "Save a report in chat to edit and download it here.")}</p></div>}
      <div className="flex flex-col gap-4">
        {[
          ...sessions.filter(session => statuses[session.session_id] !== "review").map(renderResult),
          reviewCount > 0 && <button key="review-toggle" type="button" aria-expanded={showReview} onClick={() => setShowReview(value => !value)} className="glass-panel flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm"><span>{zh ? `需核对的来源（${reviewCount}）` : `Sources to review (${reviewCount})`}</span><span className="shrink-0 text-primary">{showReview ? (zh ? "收起" : "Collapse") : (zh ? "展开核对" : "Review")}</span></button>,
          ...sessions.filter(session => statuses[session.session_id] === "review").map(renderResult),
        ]}
      </div>
      {nextCursor && <button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-secondary mt-6">{isLoadingMore ? (zh ? "正在加载…" : "Loading…") : (zh ? "加载更多成果" : "Load more results")}</button>}
    </main>
  );
}

export default function ResultsPage() {
  return <WorkspaceGate content={ResultsContent} />;
}
