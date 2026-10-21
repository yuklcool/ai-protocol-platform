"use client";

import { useI18n } from "@/contexts/I18nContext";

export function SessionFeedback({ error, isLoading, empty, retry }: {
  error: string | null;
  isLoading: boolean;
  empty: boolean;
  retry: () => void;
}) {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  return <>
    {error && <div role="alert" className="glass-panel flex flex-wrap items-center justify-between gap-3 p-5">
      <p className="text-sm text-foreground">{zh ? "无法加载会话。已有会话仍保留，请重试。" : "Could not load sessions. Existing sessions are kept. Please retry."}</p>
      <button type="button" onClick={retry} className="button-ghost px-3 py-2 text-sm">{zh ? "重试" : "Retry"}</button>
    </div>}
    {isLoading && <p role="status" className="text-sm text-muted-foreground">{zh ? "正在加载会话…" : "Loading sessions…"}</p>}
    {!error && !isLoading && empty && <p className="glass-panel p-6 text-sm text-muted-foreground">{zh ? "还没有会话，开始一项任务吧。" : "No sessions yet. Start a task to begin."}</p>}
  </>;
}
