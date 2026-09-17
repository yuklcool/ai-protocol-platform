"use client";

import { useEffect, useState } from "react";
import type { A2uiArtifactEntry } from "@/providers/SurfaceRegistry";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";
import type { Locale } from "@/lib/i18n";

function formatRelative(ts: number, now: number, locale: Locale): string {
  if (!ts) return "";
  const diff = Math.max(0, now - ts);
  const seconds = Math.floor(diff / 1000);
  if (seconds < 5) return translateChat(locale, "time.justNow");
  if (seconds < 60) return translateChat(locale, "time.secondsAgo", { count: seconds });
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return translateChat(locale, "time.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return translateChat(locale, "time.hoursAgo", { count: hours });
  return new Date(ts).toLocaleDateString(locale === "zh-CN" ? "zh-CN" : "en");
}

export function WorkbenchIndex({
  artifacts,
  onOpen,
  heading,
}: {
  artifacts: A2uiArtifactEntry[];
  onOpen: (surfaceId: string) => void;
  heading?: string;
}) {
  const { locale } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const summaryKey = artifacts.length === 1
    ? "workbench.indexSummaryOne"
    : "workbench.indexSummaryMany";

  return (
    <div className="flex h-full flex-col overflow-auto p-3" data-testid="workbench-index">
      <div className="mb-2 px-1">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">
          {heading ?? translateChat(locale, "workbench.indexDefaultHeading")}
        </h2>
        <p className="text-xs text-muted-foreground">
          {translateChat(locale, summaryKey, { count: artifacts.length })}
        </p>
      </div>
      <ol className="flex flex-col gap-1.5">
        {artifacts.map((artifact) => (
          <li key={artifact.surfaceId}>
            <button
              type="button"
              onClick={() => onOpen(artifact.surfaceId)}
              className="group flex w-full items-start gap-3 rounded-lg border border-border bg-muted/10 px-3 py-2.5 text-left transition-colors hover:border-primary/50 hover:bg-muted/30"
            >
              <span className="mt-0.5 shrink-0 rounded-md bg-primary/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-primary">
                {artifact.kind || translateChat(locale, "shell.result")}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-foreground">
                  {artifact.title || artifact.kind || translateChat(locale, "shell.result")}
                </span>
                {artifact.description && (
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                    {artifact.description}
                  </span>
                )}
              </span>
              <span className="mt-0.5 flex shrink-0 items-center gap-2">
                <time className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
                  {formatRelative(artifact.createdAt, now, locale)}
                </time>
                <span
                  aria-hidden
                  className="text-xs text-muted-foreground/50 transition-colors group-hover:text-primary"
                >
                  {translateChat(locale, "workbench.open")}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
