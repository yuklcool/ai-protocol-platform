"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Boxes,
  Building2,
  Database,
  FileSearch,
  FlaskConical,
  LayoutDashboard,
  PanelsTopLeft,
  Plug,
  ScrollText,
  Settings2,
  ShieldCheck,
  Sparkles,
  UsersRound,
  Wrench,
} from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BRANDING } from "@/lib/branding";
import { UserMenu } from "./UserMenu";

type NavigationItem = {
  href: string;
  zh: string;
  en: string;
  icon: typeof Bot;
};

type NavigationGroup = {
  zh: string;
  en: string;
  items: NavigationItem[];
};

export const CONSOLE_NAVIGATION: NavigationGroup[] = [
  {
    zh: "概览",
    en: "Overview",
    items: [
      { href: "/", zh: "工作台", en: "Workspace", icon: LayoutDashboard },
    ],
  },
  {
    zh: "智能体",
    en: "Agent",
    items: [
      { href: "/agent", zh: "Root Agent 设置", en: "Root Agent Settings", icon: Bot },
    ],
  },
  {
    zh: "资源",
    en: "Resources",
    items: [
      { href: "/skills", zh: "Skills", en: "Skills", icon: Sparkles },
      { href: "/admin/tool-permissions", zh: "Tools", en: "Tools", icon: Wrench },
      { href: "/admin/mcp-servers", zh: "MCP Servers", en: "MCP Servers", icon: Plug },
      { href: "/admin/model-providers", zh: "Models", en: "Models", icon: Boxes },
      { href: "/dev/file-browser", zh: "Knowledge", en: "Knowledge", icon: Database },
    ],
  },
  {
    zh: "管理",
    en: "Administration",
    items: [
      { href: "/admin/tenants", zh: "Tenants", en: "Tenants", icon: Building2 },
      { href: "/admin/users", zh: "Users", en: "Users", icon: UsersRound },
      { href: "/admin/groups", zh: "Groups", en: "Groups", icon: ShieldCheck },
      { href: "/admin/analytics", zh: "Usage", en: "Usage", icon: Activity },
      { href: "/admin/audit", zh: "Audit", en: "Audit", icon: ScrollText },
    ],
  },
  {
    zh: "开发者",
    en: "Developer",
    items: [
      { href: "/dev/a2ui", zh: "A2UI Playground", en: "A2UI Playground", icon: PanelsTopLeft },
      { href: "/dev/mcp-apps", zh: "MCP Apps", en: "MCP Apps", icon: Plug },
      { href: "/dev/rich-media", zh: "Rich Media", en: "Rich Media", icon: FileSearch },
      { href: "/workshop", zh: "Workshop", en: "Workshop", icon: FlaskConical },
    ],
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname.startsWith("/chat") || pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function label(item: { zh: string; en: string }, isChinese: boolean) {
  return isChinese ? item.zh : item.en;
}

function NavLink({ item, pathname, isChinese }: { item: NavigationItem; pathname: string; isChinese: boolean }) {
  const active = isActive(pathname, item.href);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`console-nav-item ${active ? "console-nav-item-active" : ""}`}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="truncate">{label(item, isChinese)}</span>
    </Link>
  );
}

export function ConsoleSidebar() {
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const isChinese = locale.startsWith("zh");

  return (
    <aside className="console-sidebar" aria-label={isChinese ? "主导航" : "Primary navigation"}>
      <div className="console-sidebar-brand">
        <Link href="/" className="flex min-w-0 items-center gap-2.5" aria-label={BRANDING.appName}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRANDING.logo.chatAvatar} alt="" className="h-7 w-7 rounded-md" />
          <span className="truncate text-sm font-semibold tracking-tight">{BRANDING.appName}</span>
        </Link>
        <span className="console-brand-status" aria-label={isChinese ? "系统在线" : "System online"} />
      </div>

      <nav className="console-sidebar-nav">
        {CONSOLE_NAVIGATION.map((group) => (
          <div key={group.en} className="console-nav-group">
            <p className="console-nav-label">{label(group, isChinese)}</p>
            <div className="space-y-0.5">
              {group.items.map((item) => <NavLink key={item.href} item={item} pathname={pathname} isChinese={isChinese} />)}
            </div>
          </div>
        ))}
      </nav>

      <div className="console-sidebar-footer">
        <Link href="/admin/settings" className="console-nav-item">
          <Settings2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{isChinese ? "平台设置" : "Platform settings"}</span>
        </Link>
        <div className="mt-2 flex items-center justify-between px-2">
          <LanguageSwitcher compact />
          <UserMenu />
        </div>
        <div className="console-runtime-card">
          <span className="console-runtime-dot" />
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">{isChinese ? "Root Agent" : "Root Agent"}</p>
            <p className="truncate text-[11px] text-muted-foreground">{isChinese ? "统一运行时" : "Unified runtime"}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

export function ConsoleMobileNav() {
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const isChinese = locale.startsWith("zh");
  const items = CONSOLE_NAVIGATION.flatMap((group) => group.items).slice(0, 8);
  return (
    <div className="console-mobile-nav no-scrollbar">
      {items.map((item) => {
        const Icon = item.icon;
        const active = isActive(pathname, item.href);
        return (
          <Link key={item.href} href={item.href} className={active ? "console-mobile-link console-mobile-link-active" : "console-mobile-link"}>
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {label(item, isChinese)}
          </Link>
        );
      })}
    </div>
  );
}
