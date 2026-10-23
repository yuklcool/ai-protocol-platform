import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
import { fetchWithAuth } from "@/lib/apiClient";
import { useLandingTarget } from "@/hooks/useLandingTarget";

const mockFetch = vi.mocked(fetchWithAuth);

describe("useLandingTarget", () => {
  beforeEach(() => { mockFetch.mockReset(); });

  it("未启用时等待认证且不请求后端", () => {
    const { result } = renderHook(() => useLandingTarget(false));
    expect(result.current).toEqual({ kind: "loading" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("登录后稳定进入任务对话，不强制恢复最近会话", () => {
    const { result } = renderHook(() => useLandingTarget(true));
    expect(result.current).toEqual({ kind: "chat", href: "/chat/root-agent" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("后端不可用也不退回宣传页，并响应退出登录", () => {
    mockFetch.mockRejectedValue(new Error("offline"));
    const { result, rerender } = renderHook(({ enabled }) => useLandingTarget(enabled), { initialProps: { enabled: true } });
    expect(result.current).toEqual({ kind: "chat", href: "/chat/root-agent" });
    rerender({ enabled: false });
    expect(result.current).toEqual({ kind: "loading" });
    rerender({ enabled: true });
    expect(result.current).toEqual({ kind: "chat", href: "/chat/root-agent" });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
