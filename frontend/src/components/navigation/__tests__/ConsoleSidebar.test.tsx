import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsoleMobileNav, ConsoleSidebar } from "../ConsoleSidebar";
import SettingsPage from "@/app/settings/page";

const state = vi.hoisted(() => ({ pathname: "/chat/root-agent", locale: "en", user: { uid: "u1" }, scope: { state: "platform", isAdmin: true, isPlatform: true, recheck: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: state.user, loading: false }) }));
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale: state.locale }) }));
vi.mock("@/hooks/useAdminScope", () => ({ useAdminScope: () => state.scope }));
vi.mock("@/hooks/useSkillSessions", () => ({ useSkillSessions: () => ({ sessions: [], isLoading: false, error: null, refetch: vi.fn() }) }));
vi.mock("@/components/LanguageSwitcher", () => ({ LanguageSwitcher: () => null }));
vi.mock("../UserMenu", () => ({ UserMenu: () => null }));

beforeEach(() => {
  state.pathname = "/chat/root-agent"; state.locale = "en";
  Object.assign(state.scope, { state: "platform", isAdmin: true, isPlatform: true });
  vi.clearAllMocks();
});

describe.each([["desktop", ConsoleSidebar], ["mobile", ConsoleMobileNav]] as const)("%s navigation", (_, Component) => {
  function show() {
    render(<Component />);
    if (Component === ConsoleMobileNav) fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
  }
  it.each([
    ["/", "/chat/root-agent"], ["/chat/root-agent", "/chat/root-agent"], ["/chat/other", "/chat/root-agent"],
    ["/sessions", "/sessions"], ["/results/report", "/results"], ["/documents", "/documents"],
    ["/skills/studio/a", "/skills"], ["/settings/personal", "/settings"], ["/agent/profile", "/settings"],
    ["/admin/model-providers", "/settings"], ["/admin/settings", "/settings"], ["/setup", "/settings"],
    ["/administrator", null], ["/chatty", null],
  ])("%s highlights %s", (path, href) => {
    state.pathname = path!; show();
    expect(screen.queryAllByRole("link", { current: "page" }).map(link => link.getAttribute("href"))).toEqual(href ? [href] : []);
  });
  it("keeps daily navigation compact and opens chat from the brand", () => {
    show();
    for (const name of ["Chat", "Results", "Documents", "Capabilities", "Settings", "View all"]) expect(screen.getByRole("link", { name })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to chat/ })).toHaveAttribute("href", "/chat/root-agent");
    expect(screen.queryByRole("link", { name: "Model services" })).not.toBeInTheDocument();
  });
});

it("closes mobile navigation after selecting a destination", () => {
  render(<ConsoleMobileNav />);
  fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
  const link = screen.getByRole("link", { name: "Documents" });
  link.addEventListener("click", event => event.preventDefault(), { once: true });
  fireEvent.click(link);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("retains admin and platform access conditions in settings", () => {
  state.scope.isPlatform = false;
  const view = render(<SettingsPage />);
  expect(screen.getByRole("link", { name: /MCP connections/ })).toHaveAttribute("href", "/admin/mcp-servers");
  expect(screen.queryByRole("link", { name: /Model services/ })).not.toBeInTheDocument();
  state.scope.isAdmin = false;
  view.rerender(<SettingsPage />);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link", { name: /Personal preferences/ })).toHaveAttribute("href", "/settings/personal");
});
it("offers a retry when settings permissions fail", () => {
  Object.assign(state.scope, { state: "error", isAdmin: false, isPlatform: false });
  render(<SettingsPage />);
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(state.scope.recheck).toHaveBeenCalledOnce();
  expect(screen.getAllByRole("link")).toHaveLength(1);
});
