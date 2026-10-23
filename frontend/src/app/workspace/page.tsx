"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Plus, ListChecks, Clock3, CircleAlert, CheckCheck } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionCard } from "@/components/workspace/SessionCard";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";

const views = [
  { status: "", zh: "全部任务", en: "All tasks", icon: ListChecks },
  { status: "needs_input", zh: "待确认 / 补充", en: "Needs input", icon: CircleAlert },
  { status: "running", zh: "执行中", en: "Running", icon: Clock3 },
  { status: "completed", zh: "已完成", en: "Completed", icon: CheckCheck },
  { status: "failed", zh: "执行失败", en: "Failed", icon: CircleAlert },
];

function WorkspaceContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [status, setStatus] = useState("");
  const { sessions, isLoading, error, refetch, nextCursor, loadMore, isLoadingMore } = useSkillSessions(null, { taskStatus: status });
  return (
    <main className="page-container workspace-page mx-auto max-w-6xl">
      <header className="page-header">
        <div><p className="page-header__eyebrow">{zh ? "你的 AI 工作空间" : "Your AI workspace"}</p><h1 className="page-header__title">{zh ? "任务概览" : "Task overview"}</h1><p className="page-header__desc">{zh ? "从一个目标开始，让每一步和每一份成果都清晰可见。" : "Start with a goal. Keep every step and every result in view."}</p></div>
        <Link href="/chat/root-agent" className="button-primary"><Plus className="h-4 w-4" />{zh ? "开始新任务" : "New task"}</Link>
      </header>
      <section className="workspace-intro glass-panel">
        <div><span className="badge badge--brand">Root Agent</span><h2 className="mt-4 text-2xl font-semibold">{zh ? "把目标交给助手，专注下一步。" : "Give your assistant a goal. Focus on what comes next."}</h2><p className="mt-3 max-w-xl text-sm text-muted-foreground">{zh ? "在对话中查看计划、确认操作、编辑报告。任务状态来自助手明确报告的计划，刷新后可继续查看。" : "Review plans, confirm actions and edit reports in conversation. Status reflects the assistant’s explicit saved plan."}</p></div>
        <div className="flex flex-wrap gap-2"><Link href="/results" className="button-secondary">{zh ? "查看我的成果" : "View results"}<ArrowUpRight className="h-4 w-4" /></Link><Link href="/skills" className="button-ghost">{zh ? "发现能力" : "Explore capabilities"}</Link></div>
      </section>
      <section className="mt-8 space-y-5" aria-labelledby="recent-sessions">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="recent-sessions">{zh ? "继续你的任务" : "Continue your tasks"}</h2><Link href="/sessions" className="button-ghost text-sm">{zh ? "搜索全部会话" : "Search all sessions"}<ArrowUpRight className="h-4 w-4" /></Link></div>
        <div className="task-tabs" role="group" aria-label={zh ? "按任务状态筛选" : "Filter tasks by status"}>{views.map(view => <button key={view.status} type="button" aria-pressed={status === view.status} onClick={() => setStatus(view.status)}><view.icon className="h-4 w-4" />{zh ? view.zh : view.en}</button>)}</div>
        <p className="text-xs text-muted-foreground">{zh ? "状态是最近一次计划报告，不代表后台正在持续执行。旧会话首次打开后会同步已有计划；未报告计划的会话保留为“未提供计划”。" : "Status is the latest plan report, not proof of a background worker. Opening an older session reconciles saved plans; sessions without one remain unplanned."}</p>
        <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{sessions.map(session => <SessionCard key={session.session_id} session={session} />)}</ul>
        {nextCursor && <button type="button" className="button-secondary" disabled={isLoadingMore} onClick={loadMore}>{isLoadingMore ? (zh ? "加载中…" : "Loading…") : (zh ? "加载更多任务" : "Load more tasks")}</button>}
      </section>
    </main>
  );
}

export default function WorkspacePage() { return <WorkspaceGate content={WorkspaceContent} />; }
