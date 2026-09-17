"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyTab } from "./EmptyTab";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

const DEFAULT_WIDTH_SCALE =
  "md:w-[520px] xl:w-[640px] 2xl:w-[760px] [@media(min-width:2000px)]:w-[860px]";

export interface WorkbenchTab {
  id: string;
  label: string;
  eyebrow?: string;
  tooltip?: string;
  badged?: boolean;
  disabled?: boolean;
  onClose?: () => void;
  content: React.ReactNode | null;
  emptyBody?: string;
}

interface WorkbenchProps {
  tabs: WorkbenchTab[];
  activeTabId: string;
  onActiveTabChange: (id: string) => void;
  className?: string;
}

export function Workbench({
  tabs,
  activeTabId,
  onActiveTabChange,
  className,
}: WorkbenchProps) {
  const tabListRef = useRef<HTMLDivElement | null>(null);
  const { locale } = useI18n();

  useEffect(() => {
    const el = tabListRef.current;
    if (!el) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const idx = tabs.findIndex((t) => t.id === activeTabId);
      if (idx === -1) return;
      const dir = e.key === "ArrowRight" ? 1 : -1;
      for (let i = 1; i <= tabs.length; i++) {
        const next = tabs[(idx + dir * i + tabs.length) % tabs.length];
        if (!next.disabled) {
          onActiveTabChange(next.id);
          return;
        }
      }
    }
    el.addEventListener("keydown", onKey);
    return () => el.removeEventListener("keydown", onKey);
  }, [tabs, activeTabId, onActiveTabChange]);

  return (
    <div
      className={cn(
        "flex shrink-0 flex-col overflow-hidden border-l border-border bg-background",
        className ?? DEFAULT_WIDTH_SCALE,
      )}
    >
      <header className="flex items-stretch border-b border-border bg-muted/10">
        <div className="flex items-center gap-3 border-r border-border px-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            {translateChat(locale, "workbench.title")}
          </span>
        </div>
        <div
          ref={tabListRef}
          role="tablist"
          aria-label={translateChat(locale, "workbench.tabsAria")}
          className="no-scrollbar flex flex-1 overflow-x-auto"
        >
          {tabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            const closable = Boolean(tab.onClose) && !tab.disabled;
            return (
              <div
                key={tab.id}
                className={cn(
                  "group relative flex shrink-0 items-stretch transition-colors",
                  isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  tab.disabled && "opacity-40",
                )}
              >
                <button
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`workbench-panel-${tab.id}`}
                  tabIndex={isActive ? 0 : -1}
                  disabled={tab.disabled}
                  title={tab.tooltip}
                  onClick={() => onActiveTabChange(tab.id)}
                  className={cn(
                    "flex max-w-[13rem] shrink-0 items-baseline gap-2 py-3 pl-4 text-left",
                    closable ? "pr-1" : "pr-4",
                    tab.disabled && "cursor-not-allowed",
                  )}
                >
                  {tab.eyebrow && (
                    <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-muted-foreground/70">
                      {tab.eyebrow}
                    </span>
                  )}
                  <span className="truncate text-sm font-semibold tracking-tight">{tab.label}</span>
                  {tab.badged && !isActive && (
                    <span
                      aria-label={translateChat(locale, "workbench.newContent")}
                      className="relative ml-0.5 flex h-1.5 w-1.5 shrink-0 items-center justify-center"
                    >
                      <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-primary/40" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
                    </span>
                  )}
                </button>
                {closable && (
                  <button
                    type="button"
                    aria-label={translateChat(locale, "workbench.closeAria", { label: tab.label })}
                    title={translateChat(locale, "workbench.closeAria", { label: tab.label })}
                    onClick={(e) => {
                      e.stopPropagation();
                      tab.onClose?.();
                    }}
                    className={cn(
                      "mr-2 flex shrink-0 items-center self-center rounded p-1 transition-opacity",
                      "hover:bg-muted hover:text-foreground",
                      "focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                      "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
                      isActive && "opacity-60 hover:opacity-100",
                    )}
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                )}
                {isActive && (
                  <span
                    aria-hidden
                    className="absolute inset-x-2 -bottom-px h-0.5 origin-center animate-in fade-in zoom-in-x-50 rounded-t-sm bg-primary duration-200"
                  />
                )}
              </div>
            );
          })}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const tabBody =
            tab.content == null && tab.emptyBody
              ? <EmptyTab title={tab.label} body={tab.emptyBody} />
              : tab.content;
          return (
            <div
              key={tab.id}
              role="tabpanel"
              id={`workbench-panel-${tab.id}`}
              aria-hidden={!isActive}
              className={cn(
                "h-full w-full overflow-auto",
                isActive ? "animate-in fade-in duration-200" : "hidden",
              )}
            >
              {tabBody}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function useTabBadges() {
  const [badged, setBadged] = useState<Record<string, boolean>>({});
  return {
    mark: (id: string) => setBadged((p) => ({ ...p, [id]: true })),
    clear: (id: string) => setBadged((p) => ({ ...p, [id]: false })),
    clearOnActivate: (id: string) =>
      setBadged((p) => (p[id] ? { ...p, [id]: false } : p)),
    isBadged: (id: string) => Boolean(badged[id]),
  };
}
