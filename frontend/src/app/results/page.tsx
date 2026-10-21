"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions, type ChatSessionSummary } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";
import { fetchWithAuth } from "@/lib/apiClient";
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
  const zh = locale.startsWith("zh");
  const [data, setData] = useState<SessionResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<number | "network" | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setData(null);
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
        if (!controller.signal.aborted) setData(body);
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
    <section aria-labelledby="selected-results-title" aria-busy={loading} className="glass-panel min-w-0 space-y-4 p-5 sm:p-6">
      <header className="space-y-2">
        <h2 id="selected-results-title" className="break-words text-xl font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{zh ? "仅展示此会话持久化的交互成果摘要；返回原对话查看内容，不会重新执行任务。" : "Persisted interactive-result summaries for this session only. Return to the conversation to view content without rerunning the task."}</p>
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
        {data.state_available && data.results.length === 0 && <p className="text-sm text-muted-foreground">{zh ? "未找到可展示的持久化交互成果摘要。上传附件、知识来源和普通聊天文本不计入此列表。" : "No persisted interactive-result summaries were found. Uploads, knowledge sources and ordinary chat text are not listed as results."}</p>}
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
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = sessions.find((session) => session.session_id === selectedId);
  const search = query.trim().toLocaleLowerCase();
  const filtered = sessions.filter((session) => [session.title, session.skill_label, session.session_id].some((value) => value?.toLocaleLowerCase().includes(search)));
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <header className="glass-panel space-y-3 p-6 sm:p-8">
        <Link href="/workspace" className="text-sm text-primary">{zh ? "返回工作台" : "Back to workspace"}</Link>
        <h1 className="text-3xl font-semibold tracking-tight">{zh ? "我的成果" : "My results"}</h1>
        <p className="max-w-[65ch] text-sm text-muted-foreground">{zh ? "先选择可访问的会话，再查看成果摘要。此处不是全部文件索引，不扫描对话全文，也不把上传附件当成成果。" : "Choose an accessible session to see its result summaries. This is not a complete file index: it does not scan transcripts or count uploads as results."}</p>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <section aria-labelledby="result-sessions-title" className="min-w-0 space-y-4">
          <h2 id="result-sessions-title" className="text-lg font-semibold">{zh ? "选择来源会话" : "Choose a source session"}</h2>
          <div className="space-y-2">
            <label htmlFor="result-session-search" className="block text-sm font-medium">{zh ? "搜索已加载会话" : "Search loaded sessions"}</label>
            <input id="result-session-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-xl border border-border bg-background px-4 py-3" />
            <p className="text-xs text-muted-foreground">{zh ? "仅搜索已加载的会话，加载更多可扩大范围。" : "Search covers loaded sessions only. Load more to extend it."}</p>
          </div>
          <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
          {!error && !isLoading && sessions.length > 0 && filtered.length === 0 && <p className="text-sm text-muted-foreground">{zh ? "已加载会话中没有匹配项。" : "No matches in loaded sessions."}</p>}
          <ul className="space-y-2">{filtered.map((session) => {
            const title = session.title || (zh ? "未命名会话" : "Untitled session");
            return <li key={session.session_id}>
              <button type="button" aria-pressed={selectedId === session.session_id} aria-label={zh ? `查看成果：${title}` : `View results: ${title}`} onClick={() => setSelectedId(session.session_id)} className={`glass-panel w-full space-y-1 p-4 text-left transition-colors hover:bg-primary/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring ${selectedId === session.session_id ? "border-primary" : ""}`}>
                <span className="block break-words font-medium">{title}</span>
                {session.skill_label && <span className="block text-xs text-muted-foreground">{session.skill_label}</span>}
              </button>
            </li>;
          })}</ul>
          {nextCursor && <button type="button" onClick={loadMore} disabled={isLoading || isLoadingMore} className="button-secondary px-4 py-2 disabled:opacity-50">{isLoadingMore ? zh ? "正在加载更多…" : "Loading more…" : zh ? "加载更多会话" : "Load more sessions"}</button>}
        </section>
        {selected ? <ResultsDetails key={selected.session_id} session={selected} /> : <p className="glass-panel p-6 text-sm text-muted-foreground">{zh ? "选择左侧会话后读取该会话的成果，不会自动遍历所有会话。" : "Select a session to load its results. Other sessions are not automatically scanned."}</p>}
      </div>
    </main>
  );
}

export default function ResultsPage() {
  return <WorkspaceGate content={ResultsContent} />;
}
