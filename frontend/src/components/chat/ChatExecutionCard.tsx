"use client";

import type { ChatExecution } from "@/lib/chatExecution";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

export function ChatExecutionCard({ execution, onStop }: { execution: ChatExecution; onStop?: () => void }) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateChat>[1]) => translateChat(locale, key);
  return (
    <section data-execution-id={execution.id} className="glass-panel my-3 w-full min-w-0 max-w-2xl overflow-hidden p-4" aria-label={t("execution.title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{t("execution.title")}</h3>
        <span role="status" className="text-xs text-muted-foreground">{t(`execution.${execution.status}`)}</span>
      </div>
      {execution.stage && execution.status === "running" && <p className="mt-2 break-words text-sm text-muted-foreground">{execution.stage}</p>}
      <ol className="mt-3 space-y-2">
        {execution.tools.map((tool) => (
          <li key={tool.id} className="flex min-w-0 items-start gap-2 text-sm">
            <span aria-hidden className={tool.status === "running" && execution.status === "running" ? "animate-pulse text-primary" : "text-muted-foreground"}>●</span>
            <span className="min-w-0 flex-1 break-all">{tool.name.replace(/_/g, " ")}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{t(tool.status === "success" ? "execution.returned" : tool.status === "error" ? "execution.noResult" : execution.status === "running" ? "execution.running" : "execution.noResult")}</span>
          </li>
        ))}
      </ol>
      {(execution.status === "interrupted" || execution.status === "cancelled" || execution.status === "failed") && (
        <p className="mt-3 text-xs text-muted-foreground">{t("execution.checkBeforeRetry")}</p>
      )}
      {execution.status === "running" && onStop && <button type="button" onClick={onStop} className="button-secondary mt-3 min-h-11 text-xs">{t("shell.stop")}</button>}
    </section>
  );
}
