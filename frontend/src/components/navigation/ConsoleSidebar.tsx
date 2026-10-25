"use client";

import Link from "next/link";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { usePathname } from "next/navigation";
import { Files, FolderOpen, Settings2, Sparkles, Menu, MessageSquare, X } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BRANDING } from "@/lib/branding";
import { UserMenu } from "./UserMenu";
import { RecentConversations } from "./RecentConversations";

export const CONSOLE_NAVIGATION = [
  { href: "/chat/root-agent", zh: "对话", en: "Chat", icon: MessageSquare },
  { href: "/results", zh: "成果", en: "Results", icon: Files },
  { href: "/documents", zh: "资料", en: "Documents", icon: FolderOpen },
  { href: "/skills", zh: "能力", en: "Capabilities", icon: Sparkles },
];
const settings = { href: "/settings", zh: "设置", en: "Settings", icon: Settings2 };

function isActive(pathname: string, href: string) {
  const matches = (path: string) => pathname === path || pathname.startsWith(`${path}/`);
  if (href === "/chat/root-agent") return pathname === "/" || matches("/chat");
  if (href === "/settings") return ["/settings", "/agent", "/admin", "/setup"].some(matches);
  return matches(href);
}

function Brand({ zh }: { zh: boolean }) {
  return <Link href="/chat/root-agent" className="flex min-w-0 flex-1 items-center gap-2.5" aria-label={`${BRANDING.appName} — ${zh ? "返回对话" : "Back to chat"}`}>
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-[var(--hairline)] bg-white shadow-[var(--shadow-1)]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={BRANDING.logo.chatAvatar} alt="" className="h-5 w-5" />
    </span>
    <span className="min-w-0"><span className="block truncate text-[13px] font-semibold tracking-tight">{BRANDING.appName}</span><span className="block text-[11px] text-[var(--text-3)]">{zh ? "个人 AI 工作台" : "Personal AI workspace"}</span></span>
  </Link>;
}

function NavLink({ item, pathname, zh }: { item: typeof settings; pathname: string; zh: boolean }) {
  const active = isActive(pathname, item.href);
  return <Link href={item.href} aria-current={active ? "page" : undefined} className={`console-nav-item ${active ? "console-nav-item-active" : ""}`}>
    <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" /><span className="truncate">{zh ? item.zh : item.en}</span>
  </Link>;
}

function Navigation({ pathname, zh }: { pathname: string; zh: boolean }) {
  return <>
    <div className="console-nav-group space-y-0.5">{CONSOLE_NAVIGATION.map(item => <NavLink key={item.href} item={item} pathname={pathname} zh={zh} />)}</div>
    <RecentConversations />
  </>;
}

export function ConsoleSidebar() {
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  return <aside className="console-sidebar" aria-label={zh ? "主导航" : "Primary navigation"}>
    <div className="console-sidebar-brand"><Brand zh={zh} /></div>
    <nav className="console-sidebar-nav"><Navigation pathname={pathname} zh={zh} /></nav>
    <div className="console-sidebar-footer">
      <NavLink item={settings} pathname={pathname} zh={zh} />
      <div className="mt-2 flex items-center justify-between gap-1 px-1"><LanguageSwitcher compact /><UserMenu /></div>
    </div>
  </aside>;
}

export function ConsoleMobileNav() {
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [open, setOpen] = useState(false);
  return <div className="console-mobile-nav">
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild><button type="button" className="button-secondary inline-flex h-11 w-11 items-center justify-center p-0" aria-label={zh ? "打开主导航" : "Open navigation"}><Menu className="h-5 w-5" /></button></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="console-drawer-overlay" />
        <Dialog.Content className="console-drawer" aria-describedby={undefined}>
          <div className="mb-6 flex items-center justify-between gap-3">
            <Dialog.Title className="text-[15px] font-semibold">{zh ? "主导航" : "Navigation"}</Dialog.Title>
            <Dialog.Close asChild><button type="button" className="button-secondary inline-flex h-11 w-11 items-center justify-center p-0" aria-label={zh ? "关闭主导航" : "Close navigation"}><X className="h-5 w-5" /></button></Dialog.Close>
          </div>
          <nav aria-label={zh ? "主导航" : "Primary navigation"} onClick={event => { if ((event.target as HTMLElement).closest("a")) setOpen(false); }}>
            <Navigation pathname={pathname} zh={zh} />
            <NavLink item={settings} pathname={pathname} zh={zh} />
          </nav>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    <div className="min-w-0 flex-1 px-1"><Brand zh={zh} /></div><LanguageSwitcher compact /><UserMenu />
  </div>;
}
