"use client";

import Link from "next/link";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  LayoutDashboard,
  History,
  Files,
  ScrollText,
  Settings2,
  Sparkles,
  UsersRound,
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

/**
 * Navigation is grouped by what the user is trying to do, not by route
 * prefix: use the agent → give it resources → administer the platform.
 * Order inside a group follows expected frequency of use.
 */
export const CONSOLE_NAVIGATION: NavigationGroup[] = [
  {
    zh: "工作区",
    en: "Workspace",
    items: [
      { href: "/workspace", zh: "工作台", en: "Workspace", icon: LayoutDashboard },
      { href: "/sessions", zh: "历史对话", en: "Conversations", icon: History },
      { href: "/results", zh: "我的成果", en: "Results", icon: Files },
      { href: "/skills", zh: "能力中心", en: "Capabilities", icon: Sparkles },
    ],
  },
  {
    zh: "平台管理",
    en: "Administration",
    items: [
      { href: "/admin", zh: "就绪与资源接入", en: "Readiness and resources", icon: Bot },
      { href: "/admin/users", zh: "用户管理", en: "Users", icon: UsersRound },
      { href: "/admin/analytics", zh: "用量统计", en: "Usage", icon: Activity },
      { href: "/admin/audit", zh: "审计日志", en: "Audit", icon: ScrollText },
    ],
  },
];

function isActive(pathname: string, href: string) {
  const matches = (path: string) =>
    pathname === path || pathname.startsWith(`${path}/`);

  if (href === "/workspace") {
    return pathname === "/" || matches("/workspace") || matches("/chat");
  }
  if (href === "/admin") {
    const specificPaths = [
      ...CONSOLE_NAVIGATION.flatMap((group) => group.items.map((item) => item.href)),
      "/admin/settings",
    ].filter((path) => path.startsWith("/admin/"));
    return (
      matches("/agent") ||
      (matches("/admin") && !specificPaths.some(matches))
    );
  }
  return matches(href);
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
      return !(item.href === "/admin" || item.href.startsWith("/admin/")) || isAdmin;
    }),
  })).filter((group) => group.items.length > 0);
}

function Brand({ isChinese }: { isChinese: boolean }) {
  return (
    <Link
      href="/workspace"
      className="flex min-w-0 flex-1 items-center gap-2.5"
      aria-label={`${BRANDING.appName} — ${isChinese ? "返回工作台" : "Back to workspace"}`}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-[var(--hairline)] bg-white shadow-[var(--shadow-1)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={BRANDING.logo.chatAvatar} alt="" className="h-5 w-5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold leading-tight tracking-tight">
          {BRANDING.appName}
        </span>
        <span className="block truncate text-[11px] leading-tight text-[var(--text-3)]">
          {isChinese ? "统一智能体运行时" : BRANDING.tagline}
        </span>
      </span>
    </Link>
  );
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
  const text = label(item, isChinese);
  return (
    <Link
      href={item.href}
      title={text}
      aria-current={active ? "page" : undefined}
      className={`console-nav-item ${active ? "console-nav-item-active" : ""}`}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="truncate">{text}</span>
    </Link>
  );
}

function RuntimeCard({ isChinese }: { isChinese: boolean }) {
  return (
    <div className="console-runtime-card">
      <Bot className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      <div className="min-w-0">
        <p className="truncate text-[12px] font-semibold leading-tight">
          Root Agent
        </p>
        <p className="truncate text-[11px] leading-tight text-[var(--text-3)]">
          {isChinese ? "模型与能力由平台配置" : "Platform-managed capabilities"}
        </p>
      </div>
    </div>
  );
}

export function ConsoleSidebar() {
  const scope = useAdminScope();
  const pathname = usePathname() || "/";
  const { locale } = useI18n();
  const isChinese = locale.startsWith("zh");
  const groups = visibleNavigation(scope.isAdmin, scope.isPlatform);

  return (
    <aside
      className="console-sidebar"
      aria-label={isChinese ? "主导航" : "Primary navigation"}
    >
      <div className="console-sidebar-brand">
        <Brand isChinese={isChinese} />
      </div>

      <nav className="console-sidebar-nav">
        {groups.map((group) => (
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
          <Link
            href="/admin/settings"
            aria-current={isActive(pathname, "/admin/settings") ? "page" : undefined}
            className={`console-nav-item ${
              isActive(pathname, "/admin/settings")
                ? "console-nav-item-active"
                : ""
            }`}
          >
            <Settings2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="truncate">
              {isChinese ? "平台设置" : "Platform settings"}
            </span>
          </Link>
        )}
        {scope.state === "error" && (
          <button
            type="button"
            onClick={() => void scope.recheck()}
            className="mt-1 px-2 text-left text-[11px] text-[var(--danger)]"
          >
            {isChinese
              ? "权限加载失败，点击重试"
              : "Permissions unavailable. Retry"}
          </button>
        )}
        <div className="mt-2 flex items-center justify-between gap-1 px-1">
          <LanguageSwitcher compact />
          <UserMenu />
        </div>
        <RuntimeCard isChinese={isChinese} />
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
          <button
            type="button"
            className="button-secondary inline-flex h-10 w-10 items-center justify-center p-0"
            aria-label={isChinese ? "打开主导航" : "Open navigation"}
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="console-drawer-overlay" />
          <Dialog.Content className="console-drawer" aria-describedby={undefined}>
            <div className="mb-6 flex items-center justify-between gap-3">
              <Dialog.Title className="text-[15px] font-semibold">
                {isChinese ? "主导航" : "Navigation"}
              </Dialog.Title>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="button-secondary inline-flex h-10 w-10 items-center justify-center p-0"
                  aria-label={isChinese ? "关闭主导航" : "Close navigation"}
                >
                  <X className="h-5 w-5" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>
            <nav
              aria-label={isChinese ? "主导航" : "Primary navigation"}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("a")) setOpen(false);
              }}
            >
              {groups.map((group) => (
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
              {scope.isPlatform && (
                <Link href="/admin/settings" aria-current={isActive(pathname, "/admin/settings") ? "page" : undefined} className={`console-nav-item mt-6 ${isActive(pathname, "/admin/settings") ? "console-nav-item-active" : ""}`}>
                  <Settings2 className="h-4 w-4" aria-hidden="true" />
                  {isChinese ? "平台设置" : "Settings"}
                </Link>
              )}
            </nav>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="min-w-0 flex-1 px-1">
        <Brand isChinese={isChinese} />
      </div>
      <LanguageSwitcher compact />
      <UserMenu />
    </div>
  );
}
