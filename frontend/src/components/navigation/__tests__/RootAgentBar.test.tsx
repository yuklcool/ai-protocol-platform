import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RootAgentBar } from "../RootAgentBar";
import { translate } from "@/lib/i18n";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  isPlatform: false,
  locale: "en" as "en" | "zh-CN",
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));
vi.mock("@/hooks/useAdminScope", () => ({
  useAdminScope: () => ({ isPlatform: navigation.isPlatform }),
}));
vi.mock("@/contexts/I18nContext", () => ({
  useI18n: () => ({ locale: navigation.locale }),
}));
vi.mock("../UserMenu", () => ({
  UserMenu: () => <button aria-label="测试账号菜单" />,
}));

function renderBar() {
  render(<RootAgentBar skills={[]} currentSkillId="root-agent" />);
}

describe("RootAgentBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.isPlatform = false;
    navigation.locale = "en";
  });

  it("品牌明确返回工作台，保留能力入口和账号菜单", () => {
    renderBar();
    expect(screen.getByRole("link", { name: "Back to workspace" })).toHaveAttribute("href", "/workspace");
    expect(screen.getByRole("link", { name: translate("en", "rootAgent.bar.skills") })).toHaveAttribute("href", "/skills");
    expect(screen.getByRole("button", { name: "测试账号菜单" })).toBeInTheDocument();
  });

  it("新对话仍进入 Root Agent 聊天", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: translate("en", "rootAgent.bar.newChat") }));
    expect(navigation.push).toHaveBeenCalledOnce();
    expect(navigation.push).toHaveBeenCalledWith("/chat/root-agent");
  });

  it("普通用户不显示 Root Agent 配置入口", () => {
    renderBar();
    expect(screen.queryByRole("link", { name: translate("en", "rootAgent.bar.configure") })).not.toBeInTheDocument();
  });

  it("平台管理员保留 Root Agent 配置入口", () => {
    navigation.isPlatform = true;
    renderBar();
    expect(screen.getByRole("link", { name: translate("en", "rootAgent.bar.configure") })).toHaveAttribute("href", "/agent");
  });

  it("中文品牌明确返回工作台", () => {
    navigation.locale = "zh-CN";
    renderBar();
    expect(screen.getByRole("link", { name: "返回工作台" })).toHaveAttribute("href", "/workspace");
  });
});
