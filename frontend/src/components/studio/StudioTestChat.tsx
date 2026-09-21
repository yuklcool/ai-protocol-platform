"use client";

import {
  AlertCircle,
  ArrowRightLeft,
  Bot,
  CheckCircle2,
  ChevronDown,
  Loader2,
  RefreshCw,
  Send,
  Square,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio, type SkillStudioTranslationKey } from "@/lib/i18n/skillStudio";
import { AGUIProvider } from "@/providers/AGUIProvider";
import { useSkillAgent } from "@/hooks/useSkillAgent";

export function StudioTestChat({
  skillId,
  isDirty,
}: {
  skillId?: string;
  isDirty: boolean;
}) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);

  if (!skillId) {
    return <SaveBeforeTesting />;
  }

  return (
    <AGUIProvider
      agentId="root-agent"
      skillId={skillId}
      capabilityHint={skillId}
    >
      <StudioTestChatInner isDirty={isDirty} />
    </AGUIProvider>
  );
}

function SaveBeforeTesting() {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);
  return (
    <div className="rounded-lg border border-dashed bg-background/50 p-4">
      <div className="flex items-center gap-2 text-xs font-medium">
        <Bot className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        {t("testChat.title")}
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        {t("testChat.saveFirst")}
      </p>
    </div>
  );
}

function StudioTestChatInner({ isDirty }: { isDirty: boolean }) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);
  const {
    messages,
    toolCalls,
    delegations,
    fallbacks,
    compactions,
    thinkingContent,
    isThinking,
    stageLabel,
    resolvedModel,
    sendMessage,
    isLoading,
    error,
    clearError,
    stop,
  } = useSkillAgent();
  const [input, setInput] = useState("");
  const [traceOpen, setTraceOpen] = useState(true);

  const submit = async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    await sendMessage(text);
  };

  const hasActivity = Boolean(
    resolvedModel ||
      stageLabel ||
      toolCalls.length ||
      delegations.length ||
      fallbacks.length ||
      compactions.length ||
      error,
  );

  return (
    <div className="rounded-lg border bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
            <Bot className="h-3.5 w-3.5 text-primary" aria-hidden />
            <span className="truncate">{t("testChat.title")}</span>
          </div>
          {isLoading ? (
            <span className="inline-flex items-center gap-1 text-[10px] text-primary">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              {t("testChat.running")}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600">
              <CheckCircle2 className="h-3 w-3" aria-hidden />
              {t("testChat.savedRuntime")}
            </span>
          )}
        </div>
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
          {isDirty ? t("testChat.unsavedHint") : t("testChat.savedHint")}
        </p>
      </div>

      <div className="max-h-72 min-h-32 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && !isThinking && (
          <p className="py-6 text-center text-xs leading-5 text-muted-foreground">
            {t("testChat.empty")}
          </p>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={message.role === "user" ? "ml-6 rounded-md bg-primary/10 p-2 text-xs" : "mr-3 rounded-md border p-2 text-xs"}
          >
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {message.role === "user" ? t("testChat.you") : t("testChat.assistant")}
            </p>
            <p className="whitespace-pre-wrap leading-5">{message.content || t("testChat.noText")}</p>
          </div>
        ))}
        {isThinking && (
          <div className="mr-3 rounded-md border border-primary/20 bg-primary/5 p-2 text-xs">
            <div className="flex items-center gap-2 text-primary">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              <span>{stageLabel || t("testChat.thinking")}</span>
            </div>
            {thinkingContent && <p className="mt-2 whitespace-pre-wrap text-muted-foreground">{thinkingContent}</p>}
          </div>
        )}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">{error.message}</span>
            <button type="button" onClick={clearError} className="shrink-0 underline">{t("testChat.dismiss")}</button>
          </div>
        )}
      </div>

      <div className="border-t p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            rows={2}
            disabled={isLoading}
            placeholder={t("testChat.placeholder")}
            aria-label={t("testChat.placeholder")}
            className="min-w-0 flex-1 resize-none rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:border-primary disabled:opacity-60"
          />
          {isLoading ? (
            <button type="button" onClick={stop} className="rounded-md border p-2 text-xs hover:bg-muted" aria-label={t("testChat.stop")}>
              <Square className="h-3.5 w-3.5" aria-hidden />
            </button>
          ) : (
            <button type="button" onClick={() => void submit()} disabled={!input.trim()} className="rounded-md bg-primary p-2 text-primary-foreground disabled:opacity-50" aria-label={t("testChat.send")}>
              <Send className="h-3.5 w-3.5" aria-hidden />
            </button>
          )}
        </div>
      </div>

      <div className="border-t">
        <button type="button" onClick={() => setTraceOpen((open) => !open)} className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium hover:bg-muted/50">
          <span className="inline-flex items-center gap-2"><RefreshCw className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />{t("testChat.trace")}</span>
          <ChevronDown className={`h-3.5 w-3.5 transition ${traceOpen ? "rotate-180" : ""}`} aria-hidden />
        </button>
        {traceOpen && (
          <div className="space-y-2 border-t px-4 py-3 text-[11px]">
            <TraceRow label={t("testChat.model")} value={resolvedModel || t("testChat.notStarted")} />
            <TraceRow label={t("testChat.stage")} value={stageLabel || (isLoading ? t("testChat.running") : t("testChat.idle"))} />
            {!hasActivity && <p className="text-muted-foreground">{t("testChat.noActivity")}</p>}
            {toolCalls.map((call) => (
              <div key={call.id} className="flex items-start gap-2 text-muted-foreground">
                <Wrench className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{call.name}</span>
                <span className={call.status === "error" ? "text-destructive" : call.status === "running" ? "text-primary" : "text-emerald-600"}>{call.status}</span>
              </div>
            ))}
            {delegations.map((item) => (
              <div key={item.id} className="flex items-start gap-2 text-muted-foreground">
                <ArrowRightLeft className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                <span className="truncate">{item.parent} → {item.targetDisplay || item.target}</span>
              </div>
            ))}
            {fallbacks.map((item) => (
              <p key={item.id} className="text-amber-600">{t("testChat.fallback")}: {item.fromModel} → {item.toModel}</p>
            ))}
            {compactions.map((item) => (
              <p key={item.id} className="text-muted-foreground">{t("testChat.compaction")}: {item.eventsCompacted}</p>
            ))}
            {error && <p className="text-destructive">{t("testChat.error")}: {error.rawMessage}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-2"><span className="text-muted-foreground">{label}</span><span className="max-w-[170px] truncate font-mono">{value}</span></div>;
}
