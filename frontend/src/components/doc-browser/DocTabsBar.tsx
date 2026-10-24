"use client";

import { useRef } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { DocTab, type DocTabData } from "./DocTab";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface DocTabsBarProps {
  tabs: DocTabData[];
  activeTabId: string | null;
  showBrowser: boolean;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onToggleInclude: (id: string) => void;
  onToggleBrowser: () => void;
}

export function DocTabsBar({
  tabs,
  activeTabId,
  showBrowser,
  onSelect,
  onClose,
  onToggleInclude,
  onToggleBrowser,
}: DocTabsBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { locale } = useI18n();

  return (
    <div className="app-toolbar flex min-h-10 items-stretch">
      {/* Browser toggle */}
      <button
        type="button"
        onClick={onToggleBrowser}
        id="chat-resource-toggle"
        aria-controls="chat-resource-sidebar"
        aria-expanded={showBrowser}
        className={[
          "flex shrink-0 items-center gap-2 border-r px-3 text-xs text-muted-foreground hover:bg-accent hover:text-foreground",
          showBrowser ? "bg-accent/50 text-foreground" : "",
        ].join(" ")}
        title={translateChat(locale, showBrowser ? "sidebar.close" : "sidebar.open")}
        aria-label={translateChat(locale, showBrowser ? "sidebar.close" : "sidebar.open")}
      >
        {showBrowser ? (
          <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
        ) : (
          <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
        )}
        <span>{translateChat(locale, "sidebar.trigger")}</span>
      </button>

      {/* Tab strip — horizontally scrollable, no scrollbar */}
      <div
        ref={scrollRef}
        role="tablist"
        className="flex min-w-0 flex-1 overflow-x-auto"
        style={{ scrollbarWidth: "none" }}
      >
        {tabs.length === 0 && (
          <span className="flex items-center px-3 text-xs text-muted-foreground">
            尚未添加附件
          </span>
        )}
        {tabs.map((tab) => (
          <DocTab
            key={tab.id}
            tab={tab}
            isActive={tab.id === activeTabId}
            onSelect={onSelect}
            onClose={onClose}
            onToggleInclude={onToggleInclude}
          />
        ))}
      </div>

    </div>
  );
}
