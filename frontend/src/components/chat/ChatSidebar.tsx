"use client";

import { useEffect, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { BookOpen, Files, History, Sparkles, X } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface ChatSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  files: ReactNode;
  history: ReactNode;
  library?: ReactNode;
  libraryLabel?: string;
  assistant?: ReactNode;
}

export function ChatSidebar({ open, onOpenChange, files, history, library, libraryLabel, assistant }: ChatSidebarProps) {
  const { locale } = useI18n();
  const [mobile, setMobile] = useState(false);
  const [activeTab, setActiveTab] = useState("files");
  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    try { setActiveTab(sessionStorage.getItem("aitana.sidebar.tab") || "files"); } catch { /* Optional browser preference. */ }
  }, []);

  const tabs = [
    { id: "files", label: translateChat(locale, "sidebar.files"), icon: Files, content: files },
    { id: "history", label: translateChat(locale, "sidebar.history"), icon: History, content: history },
    ...(library ? [{ id: "library", label: libraryLabel || translateChat(locale, "shell.library"), icon: BookOpen, content: library }] : []),
    ...(assistant ? [{ id: "assistant", label: translateChat(locale, "sidebar.assistant"), icon: Sparkles, content: assistant }] : []),
  ];
  const selected = tabs.some(tab => tab.id === activeTab) ? activeTab : "files";
  const title = translateChat(locale, "sidebar.title");
  function selectTab(id: string) {
    setActiveTab(id);
    try { sessionStorage.setItem("aitana.sidebar.tab", id); } catch { /* Optional browser preference. */ }
  }
  if (!open) return null;

  const content = <>
    <header className="flex shrink-0 items-center justify-between gap-3 px-4 py-3">
      {mobile ? <Dialog.Title className="text-sm font-semibold">{title}</Dialog.Title> : <h2 className="text-sm font-semibold">{title}</h2>}
      <button type="button" onClick={() => onOpenChange(false)} className="button-ghost inline-flex h-11 w-11 items-center justify-center p-0" aria-label={translateChat(locale, "sidebar.close")}>
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </header>
    <div role="tablist" aria-label={title} className="chat-resource-tabs mx-3 mb-3 flex shrink-0 gap-1 rounded-xl bg-muted p-1">
      {tabs.map((tab, index) => <button
        key={tab.id} type="button" role="tab" id={`chat-resource-tab-${tab.id}`} aria-controls={`chat-resource-panel-${tab.id}`}
        aria-selected={selected === tab.id} tabIndex={selected === tab.id ? 0 : -1}
        onClick={() => selectTab(tab.id)}
        onKeyDown={event => {
          let target: number;
          switch (event.key) {
            case "ArrowRight": target = (index + 1) % tabs.length; break;
            case "ArrowLeft": target = (index - 1 + tabs.length) % tabs.length; break;
            case "Home": target = 0; break;
            case "End": target = tabs.length - 1; break;
            default: return;
          }
          event.preventDefault();
          selectTab(tabs[target].id);
          document.getElementById(`chat-resource-tab-${tabs[target].id}`)?.focus();
        }}
        className="flex min-h-11 min-w-0 flex-1 items-center justify-center gap-2 rounded-lg px-2 text-xs font-medium text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        <tab.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="truncate">{tab.label}</span>
      </button>)}
    </div>
    {tabs.map(tab => <section key={tab.id} id={`chat-resource-panel-${tab.id}`} role="tabpanel" aria-labelledby={`chat-resource-tab-${tab.id}`} hidden={selected !== tab.id} className={selected === tab.id ? "flex min-h-0 flex-1 flex-col overflow-hidden" : "hidden"}>
      {tab.content}
    </section>)}
  </>;

  if (!mobile) return <aside id="chat-resource-sidebar" className="chat-resource-sidebar" aria-label={title}>{content}</aside>;
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="chat-resource-overlay" />
      <Dialog.Content id="chat-resource-sidebar" className="chat-resource-sidebar chat-resource-drawer" aria-describedby={undefined}
        onCloseAutoFocus={event => { event.preventDefault(); document.getElementById("chat-resource-toggle")?.focus(); }}>
        {content}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
