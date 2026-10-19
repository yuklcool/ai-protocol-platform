"use client";

import Link from "next/link";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Boxes,
  Building2,
  LayoutDashboard,
  Plug,
  ScrollText,
  Settings2,
  ShieldCheck,
  Sparkles,
  UsersRound,
  Wrench,
  Menu,
  X,
} from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BRANDING } from "@/lib/branding";
import { UserMenu } from "./UserMenu";
import { useAdminScope } from "@/hooks/useAdminScope";

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
      {
        href: "/agent",
        zh: "Root Agent 设置",
        en: "Root Agent Settings",
        icon: Bot,
      },
    ],
  },
  {
    zh: "资源",
    en: "Resources",
    items: [
      { href: "/skills", zh: "技能管理", en: "Skills", icon: Sparkles },
      {
        href: "/admin/mcp-servers",
        zh: "MCP 服务",
        en: "MCP Servers",
        icon: Plug,
      },
      {
        href: "/admin/model-providers",
        zh: "模型服务",
        en: "Models",
        icon: Boxes,
      },
    ],
  },
  {
    zh: "管理",
    en: "Administration",
    items: [
      {
        href: "/admin/tenants",
        zh: "租户管理",
        en: "Tenants",
        icon: Building2,
      },
      { href: "/admin/users", zh: "用户管理", en: "Users", icon: UsersRound },
      { href: "/admin/groups", zh: "权限组", en: "Groups", icon: ShieldCheck },
      { href: "/admin/analytics", zh: "用量统计", en: "Usage", icon: Activity },
      { href: "/admin/audit", zh: "审计日志", en: "Audit", icon: ScrollText },
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

export function visibleNavigation(isAdmin: boolean, isPlatform: boolean) {
  const platformPaths = new Set([
    "/agent",
    "/admin/model-providers",
    "/admin/groups",
  ]);
  return CONSOLE_NAVIGATION.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (platformPaths.has(item.href)) return isPlatform;
      return !item.href.startsWith("/admin/") || isAdmin;
    }),
  })).filter((group) => group.items.length > 0);
}

function NavLink({
  item,
  pathname,
  isChinese,
}: {
  item: NavigationItem;
  pathname: string;
  isChinese: boolean;
}) {
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
  const scope = useAdminScope();
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const isChinese = locale.startsWith("zh");

  return (
    <aside
      className="console-sidebar"
      aria-label={isChinese ? "主导航" : "Primary navigation"}
    >
      <div className="console-sidebar-brand">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5"
          aria-label={BRANDING.appName}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={BRANDING.logo.chatAvatar}
            alt=""
            className="h-7 w-7 rounded-md"
          />
          <span className="min-w-0 break-words text-xs font-semibold leading-4 tracking-tight">
            {BRANDING.appName}
          </span>
        </Link>
        <span className="console-brand-status" aria-hidden="true" />
      </div>

      <nav className="console-sidebar-nav">
        {visibleNavigation(scope.isAdmin, scope.isPlatform).map((group) => (
          <div key={group.en} className="console-nav-group">
            <p className="console-nav-label">{label(group, isChinese)}</p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  pathname={pathname}
                  isChinese={isChinese}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="console-sidebar-footer">
        {scope.isPlatform && (
          <Link href="/admin/settings" className="console-nav-item">
            <Settings2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{isChinese ? "平台设置" : "Platform settings"}</span>
          </Link>
        )}
        {scope.state === "error" && (
          <button
            type="button"
            onClick={() => void scope.recheck()}
            className="px-2 text-xs text-destructive"
          >
            {isChinese
              ? "权限加载失败，点击重试"
              : "Permissions unavailable. Retry"}
          </button>
        )}
        <div className="mt-2 flex items-center justify-between px-2">
          <LanguageSwitcher compact />
          <UserMenu />
        </div>
        <div className="console-runtime-card">
          <span className="console-runtime-dot" />
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">
              {isChinese ? "Root Agent" : "Root Agent"}
            </p>
            <p className="truncate text-[11px] text-muted-foreground">
              {isChinese ? "统一运行时" : "Unified runtime"}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}

export function ConsoleMobileNav() {
  const scope = useAdminScope();
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const isChinese = locale.startsWith("zh");
  const [open, setOpen] = useState(false);
  const groups = visibleNavigation(scope.isAdmin, scope.isPlatform);
  return (
    <div className="console-mobile-nav">
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Trigger asChild>
          <button type="button" className="button-secondary inline-flex h-10 w-10 items-center justify-center" aria-label={isChinese ? "打开主导航" : "Open navigation"}>
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="console-drawer-overlay" />
          <Dialog.Content className="console-drawer" aria-describedby={undefined}>
            <div className="mb-6 flex items-center justify-between gap-3">
              <Dialog.Title className="text-base font-semibold">{isChinese ? "主导航" : "Navigation"}</Dialog.Title>
              <Dialog.Close asChild>
                <button type="button" className="button-secondary inline-flex h-10 w-10 items-center justify-center" aria-label={isChinese ? "关闭主导航" : "Close navigation"}><X className="h-5 w-5" aria-hidden="true" /></button>
              </Dialog.Close>
            </div>
            <nav aria-label={isChinese ? "主导航" : "Primary navigation"} onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setOpen(false); }}>
              {groups.map((group) => (
                <div key={group.en} className="console-nav-group">
                  <p className="console-nav-label">{label(group, isChinese)}</p>
                  {group.items.map((item) => <NavLink key={item.href} item={item} pathname={pathname} isChinese={isChinese} />)}
                </div>
              ))}
              {scope.isPlatform && <Link href="/admin/settings" className="console-nav-item mt-6"><Settings2 className="h-4 w-4" aria-hidden="true" />{isChinese ? "平台设置" : "Settings"}</Link>}
            </nav>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Link href="/" className="min-w-0 flex-1 truncate text-sm font-semibold">{BRANDING.appName}</Link>
      <LanguageSwitcher compact />
      <UserMenu />
    </div>
  );
}
