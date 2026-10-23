import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsoleMobileNav, ConsoleSidebar, visibleNavigation } from "../ConsoleSidebar";

const navigation = vi.hoisted(() => ({
  pathname: "/workspace",
  locale: "en",
  scope: {
    state: "platform",
    isAdmin: true,
    isPlatform: true,
    recheck: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname }));
vi.mock("@/contexts/I18nContext", () => ({
  useI18n: () => ({ locale: navigation.locale }),
}));
vi.mock("@/hooks/useAdminScope", () => ({ useAdminScope: () => navigation.scope }));
vi.mock("@/components/LanguageSwitcher", () => ({ LanguageSwitcher: () => null }));
vi.mock("../UserMenu", () => ({ UserMenu: () => null }));

const routes = [
  ["/", "/chat/root-agent"],
  ["/workspace", "/workspace"],
  ["/workspace/recent", "/workspace"],
  ["/chat", "/chat/root-agent"],
  ["/chat/root-agent/session-1", "/chat/root-agent"],
  ["/sessions", "/sessions"],
  ["/sessions/session-1", "/sessions"],
  ["/results/report-1", "/results"],
  ["/skills/studio/skill-1", "/skills"],
  ["/agent", "/agent"],
  ["/agent/profile", "/agent"],
  ["/admin", "/admin"],
  ["/admin/model-providers/provider-1", "/admin/model-providers"],
  ["/admin/mcp-servers", "/admin/mcp-servers"],
  ["/admin/groups", "/admin"],
  ["/admin/clients", "/admin"],
  ["/admin/users", "/admin/users"],
  ["/admin/users/user-1", "/admin/users"],
  ["/admin/analytics", "/admin/analytics"],
  ["/admin/analytics/detail", "/admin/analytics"],
  ["/admin/audit", "/admin/audit"],
  ["/admin/audit/event-1", "/admin/audit"],
  ["/admin/settings", "/admin/settings"],
  ["/admin/settings/auth", "/admin/settings"],
  ["/admin/users-extra", "/admin"],
  ["/chatty", null],
  ["/workspace-extra", null],
  ["/agent-extra", null],
  ["/administrator", null],
  ["/settings/personal", "/settings/personal"],
] as const;

describe("控制台导航", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.pathname = "/workspace";
    navigation.locale = "en";
    Object.assign(navigation.scope, {
      state: "platform", isAdmin: true, isPlatform: true,
    });
  });

  describe.each([
    ["桌面侧栏", ConsoleSidebar],
    ["移动抽屉", ConsoleMobileNav],
  ] as const)("%s", (_name, Component) => {
    it.each(routes)("%s 仅高亮 %s", (pathname, expectedHref) => {
      navigation.pathname = pathname;
      render(<Component />);
      if (Component === ConsoleMobileNav) {
        fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
      }
      const active = screen.queryAllByRole("link", { current: "page" });
      expect(active.map((link) => link.getAttribute("href"))).toEqual(
        expectedHref ? [expectedHref] : [],
      );
    });

    it("品牌明确返回工作台", () => {
      render(<Component />);
      expect(screen.getByRole("link", { name: /Back to workspace/ })).toHaveAttribute("href", "/workspace");
    });

    it("普通用户仅显示工作区入口", () => {
      Object.assign(navigation.scope, { state: "none", isAdmin: false, isPlatform: false });
      render(<Component />);
      if (Component === ConsoleMobileNav) {
        fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
      }
      expect(screen.getByRole("link", { name: "Workspace" })).toHaveAttribute("href", "/workspace");
      expect(screen.getByRole("link", { name: "Conversations" })).toHaveAttribute("href", "/sessions");
      expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute("href", "/results");
      expect(screen.getByRole("link", { name: "Capabilities" })).toHaveAttribute("href", "/skills");
      expect(screen.getAllByRole("link").some((link) => link.getAttribute("href")?.startsWith("/admin"))).toBe(false);
    });
  });

  it("保留管理员与平台设置的独立权限条件", () => {
    navigation.scope.isPlatform = false;
    render(<ConsoleSidebar />);
    expect(screen.getByRole("link", { name: "Readiness and resources" })).toHaveAttribute("href", "/admin");
    expect(screen.queryByRole("link", { name: "Platform settings" })).not.toBeInTheDocument();
    expect(visibleNavigation(false, false).flatMap((group) => group.items.map((item) => item.href))).toEqual([
      "/chat/root-agent", "/workspace", "/sessions", "/results", "/settings/personal", "/skills",
    ]);
  });

  it("权限加载失败时保持管理入口隐藏且支持重试", () => {
    Object.assign(navigation.scope, { state: "error", isAdmin: false, isPlatform: false });
    render(<ConsoleSidebar />);
    fireEvent.click(screen.getByRole("button", { name: "Permissions unavailable. Retry" }));
    expect(navigation.scope.recheck).toHaveBeenCalledOnce();
    expect(screen.queryByRole("link", { name: "Readiness and resources" })).not.toBeInTheDocument();
  });

  it("中文品牌与导航保持本地化", () => {
    navigation.locale = "zh-CN";
    render(<ConsoleSidebar />);
    expect(screen.getByRole("link", { name: /返回工作台/ })).toHaveAttribute("href", "/workspace");
    expect(screen.getByRole("link", { name: "任务概览" })).toHaveAttribute("aria-current", "page");
  });

  it("移动端选择入口后关闭抽屉", () => {
    render(<ConsoleMobileNav />);
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const workspaceLink = screen.getByRole("link", { name: "Workspace" });
    workspaceLink.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(workspaceLink);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
