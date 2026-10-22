"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { stageWorkspaceDraft, WORKSPACE_DRAFT_LIMIT } from "@/lib/workspaceDraft";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { SessionCard } from "@/components/workspace/SessionCard";
import { SessionFeedback } from "@/components/workspace/SessionFeedback";

const EXAMPLES = [
  { zh: "总结文档并列出重点", en: "Summarize a document and key points" },
  { zh: "分析问题并提出解决建议", en: "Analyze an issue and suggest solutions" },
  { zh: "整理一份结构化报告", en: "Prepare a structured report" },
] as const;

function WorkspaceContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const { user } = useAuth();
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [draftError, setDraftError] = useState(false);
  const { sessions, isLoading, error, refetch } = useSkillSessions(null);

  function continueToChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // No implicit AG-UI call: the text is only restored to the next chat composer.
    // The server creates the user's session on the actual explicit send.
    if (!user?.uid || !stageWorkspaceDraft(goal, user.uid)) {
      setDraftError(true);
      return;
    }
    setDraftError(false);
    router.push("/chat/root-agent");
  }

  return (
    <main className="mx-auto w-full max-w-5xl space-y-8 px-4 py-10 sm:px-6">
      <header className="glass-panel space-y-6 p-6 sm:p-8">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary">
            {zh ? "AI 工作台" : "AI workspace"}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            {zh ? "今天想完成什么任务？" : "What would you like to work on?"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {zh ? "直接描述目标，再进入真实对话继续补充资料和确认发送。" : "Describe your goal, then continue in the real chat to add files and confirm sending."}
          </p>
        </div>
        <form className="space-y-3" onSubmit={continueToChat}>
          <label htmlFor="workspace-goal" className="block text-sm font-medium text-foreground">
            {zh ? "任务目标" : "Task goal"}
          </label>
          <textarea
            id="workspace-goal"
            rows={3}
            maxLength={WORKSPACE_DRAFT_LIMIT}
            value={goal}
            onChange={(event) => { setGoal(event.target.value); setDraftError(false); }}
            placeholder={zh ? "例如：分析我提供的资料，整理关键风险并生成报告草稿" : "For example: analyze my documents and draft a risk report"}
            className="glass-control w-full min-w-0 resize-y px-4 py-3 text-base"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              {zh ? "仅预填对话草稿，不会自动发送或创建后台任务。" : "Prefills the chat composer only; does not send or start a background task."}
            </p>
            <button className="button-primary px-5 py-2.5 text-sm" type="submit" disabled={!goal.trim()}>
              {zh ? "继续到对话" : "Continue in chat"} →
            </button>
          </div>
          {draftError && (
            <p role="alert" className="notice notice--danger text-sm">
              {zh ? "草稿暂时无法安全传递，请直接进入对话输入目标。" : "Unable to transfer this draft securely; open chat and type your goal there."}
            </p>
          )}
        </form>
        <div className="flex flex-wrap gap-2" aria-label={zh ? "任务目标示例" : "Example goals"}>
          {EXAMPLES.map((item) => (
            <button
              key={item.en}
              type="button"
              className="button-secondary px-3 py-2 text-xs"
              onClick={() => { setGoal(zh ? item.zh : item.en); setDraftError(false); }}
            >
              {zh ? item.zh : item.en}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 border-t border-border pt-4">
          <Link href="/chat/root-agent" className="button-secondary inline-flex px-4 py-2">
            {zh ? "开始任务" : "Start a task"}
          </Link>
          <Link href="/results" className="button-secondary inline-flex px-4 py-2">
            {zh ? "查找成果" : "Find results"}
          </Link>
          <Link href="/skills" className="button-secondary inline-flex px-4 py-2">
            {zh ? "发现能力" : "Discover capabilities"}
          </Link>
        </div>
      </header>

      <section aria-labelledby="recent-sessions" className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 id="recent-sessions" className="text-xl font-semibold text-foreground">
            {zh ? "最近会话" : "Recent sessions"}
          </h2>
          <Link href="/sessions" className="text-sm text-primary">
            {zh ? "全部会话" : "All sessions"}
          </Link>
        </div>
        <SessionFeedback error={error} isLoading={isLoading} empty={sessions.length === 0} retry={refetch} />
        <ul className="grid gap-4 sm:grid-cols-2">
          {sessions.slice(0, 6).map((session) => <SessionCard key={session.session_id} session={session} />)}
        </ul>
      </section>
    </main>
  );
}

export default function WorkspacePage() {
  return <WorkspaceGate content={WorkspaceContent} />;
}
