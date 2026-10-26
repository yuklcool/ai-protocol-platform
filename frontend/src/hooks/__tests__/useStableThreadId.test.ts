import { renderHook } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it } from "vitest";

import { useStableThreadId } from "@/hooks/useStableThreadId";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("useStableThreadId — chat-history-deep-fixes-2 Bug A' fix", () => {
  it("adopts the URL session id on initial mount when one is present", () => {
    const { result } = renderHook(() => useStableThreadId("existing-id"));
    expect(result.current).toBe("existing-id");
  });

  it("mints a fresh UUID on initial mount when URL has no session", () => {
    const { result } = renderHook(() => useStableThreadId(null));
    expect(result.current).toMatch(UUID_V4);
  });

  it("STAYS STABLE across URL writeback (URL gains the threadId we already had) — closes the visible flicker", () => {
    // Initial: no URL session → fresh UUID minted at init.
    const { result, rerender } = renderHook(
      ({ urlSessionId }: { urlSessionId: string | null }) =>
        useStableThreadId(urlSessionId),
      { initialProps: { urlSessionId: null as string | null } },
    );
    const initialThreadId = result.current;
    expect(initialThreadId).toMatch(UUID_V4);

    // URL writeback effect (in real chat page) rewrites ?session=<initialThreadId>
    rerender({ urlSessionId: initialThreadId });

    // Critical: the threadId must NOT change. AGUIProvider's useMemo
    // depends on this — a stable value means no HttpAgent rebuild,
    // which means agent.messages survives turn 1 with no flicker.
    expect(result.current).toBe(initialThreadId);
  });

  it("adopts a new id when the user navigates to a different existing thread", () => {
    const { result, rerender } = renderHook(
      ({ urlSessionId }: { urlSessionId: string | null }) =>
        useStableThreadId(urlSessionId),
      { initialProps: { urlSessionId: "session-A" as string | null } },
    );
    expect(result.current).toBe("session-A");

    rerender({ urlSessionId: "session-B" });
    expect(result.current).toBe("session-B");
  });

  it("mints a fresh UUID when URL ?session= is cleared (+ New conversation)", () => {
    const { result, rerender } = renderHook(
      ({ urlSessionId }: { urlSessionId: string | null }) =>
        useStableThreadId(urlSessionId),
      { initialProps: { urlSessionId: "existing-id" as string | null } },
    );
    const idBefore = result.current;
    expect(idBefore).toBe("existing-id");

    // User clicks "+ New conversation"
    rerender({ urlSessionId: null });

    expect(result.current).not.toBe(idBefore);
    expect(result.current).toMatch(UUID_V4);
  });

  it("never commits the previous thread under a new URL", () => {
    const committed: { urlSessionId: string | null; threadId: string }[] = [];
    const { rerender } = renderHook(({ urlSessionId }: { urlSessionId: string | null }) => {
      const threadId = useStableThreadId(urlSessionId);
      useEffect(() => { committed.push({ urlSessionId, threadId }); }, [urlSessionId, threadId]);
      return threadId;
    }, { initialProps: { urlSessionId: "session-A" as string | null } });
    rerender({ urlSessionId: "session-B" });
    rerender({ urlSessionId: null });
    expect(committed).toEqual([
      { urlSessionId: "session-A", threadId: "session-A" },
      { urlSessionId: "session-B", threadId: "session-B" },
      { urlSessionId: null, threadId: expect.stringMatching(UUID_V4) },
    ]);
  });
});
