import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const replace = vi.fn();
let authState: { user: unknown; loading: boolean } = { user: null, loading: false };
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));

import { fetchWithAuth } from "@/lib/apiClient";
import { HomeGate } from "@/components/home/HomeGate";

function gate() {
  return <HomeGate><div data-testid="landing">landing</div></HomeGate>;
}

describe("HomeGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState = { user: null, loading: false };
  });

  it("未登录保留 public 首页且不跳转", () => {
    render(gate());
    expect(screen.getByTestId("landing")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("认证尚未完成保留 public 首页", () => {
    authState.loading = true;
    render(gate());
    expect(screen.getByTestId("landing")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("登录后固定进入任务对话且不闪现宣传页", () => {
    authState = { user: { uid: "u1" }, loading: false };
    render(gate());
    expect(replace).toHaveBeenCalledWith("/chat/root-agent");
    expect(screen.queryByTestId("landing")).not.toBeInTheDocument();
    expect(screen.getByTestId("home-gate-redirecting")).toBeInTheDocument();
  });

  it("后端异常不影响入口，退出登录后恢复 public", () => {
    vi.mocked(fetchWithAuth).mockRejectedValue(new Error("offline"));
    const { rerender } = render(gate());
    authState = { user: { uid: "u1" }, loading: false };
    rerender(gate());
    expect(replace).toHaveBeenCalledWith("/chat/root-agent");
    expect(fetchWithAuth).not.toHaveBeenCalled();
    replace.mockClear();
    authState = { user: null, loading: false };
    rerender(gate());
    expect(screen.getByTestId("landing")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
