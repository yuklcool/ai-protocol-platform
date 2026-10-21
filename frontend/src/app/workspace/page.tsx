"use client";

import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionCard } from "@/components/workspace/SessionCard";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";

function WorkspaceContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const { sessions, isLoading, error, refetch } = useSkillSessions(null);
  return (
    <main className="mx-auto w-full max-w-5xl space-y-8 px-4 py-10 sm:px-6">
      <header className="glass-panel space-y-5 p-6 sm:p-8">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{zh ? "工作台" : "Workspace"}</h1>
        <p className="text-muted-foreground">{zh ? "开始新任务，或继续已有会话。" : "Start a new task or continue a conversation."}</p>
        <div className="flex flex-wrap gap-3">
          <Link href="/chat/root-agent" className="button-primary inline-flex px-4 py-2">{zh ? "开始任务" : "Start a task"}</Link>
          <Link href="/results" className="button-secondary inline-flex px-4 py-2">{zh ? "查找成果" : "Find results"}</Link>
          <Link href="/skills" className="button-secondary inline-flex px-4 py-2">{zh ? "发现能力" : "Discover capabilities"}</Link>
        </div>
      </header>
      <section aria-labelledby="recent-sessions" className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 id="recent-sessions" className="text-xl font-semibold text-foreground">{zh ? "最近会话" : "Recent sessions"}</h2>
          <Link href="/sessions" className="text-sm text-primary">{zh ? "全部会话" : "All sessions"}</Link>
        </div>
        <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
        <ul className="grid gap-4 sm:grid-cols-2">{sessions.slice(0, 6).map((session) => <SessionCard key={session.session_id} session={session} />)}</ul>
      </section>
    </main>
  );
}

export default function WorkspacePage() {
  return <WorkspaceGate content={WorkspaceContent} />;
}
