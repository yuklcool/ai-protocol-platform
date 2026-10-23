import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { useSkillSessions } from "@/hooks/useSkillSessions";

function mockOk(sessions: object[], next_cursor: string | null = null) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ sessions, next_cursor }),
  } as Response);
}

function mockError(status = 500) {
  mockFetch.mockResolvedValueOnce({ ok: false, status } as Response);
}

beforeEach(() => {
  mockFetch.mockReset();
  // Prevent unhandled rejection noise for abort
  mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ sessions: [], next_cursor: null }) } as Response);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useSkillSessions", () => {
  it("搜索翻页编码并保留条件，切换查询取消旧页且不混入新结果", async () => {
    mockOk([{ session_id: "old" }], "old-cursor");
    let resolveOld!: (response: unknown) => void;
    mockFetch.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    mockOk([{ session_id: "new" }], "new-cursor");
    const { result, rerender } = renderHook(({ q }) => useSkillSessions(null, { query: q }), { initialProps: { q: "照明 /&" } });
    await waitFor(() => expect(result.current.nextCursor).toBe("old-cursor"));
    act(() => result.current.loadMore());
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    expect(mockFetch.mock.calls[1][0]).toBe(`/api/proxy/api/sessions/search?q=${encodeURIComponent("照明 /&")}&cursor=old-cursor`);
    const oldSignal = mockFetch.mock.calls[1][1].signal as AbortSignal;
    rerender({ q: "new" });
    expect(oldSignal.aborted).toBe(true);
    await waitFor(() => expect(result.current.sessions[0]?.session_id).toBe("new"));
    await act(async () => resolveOld({ ok: true, json: async () => ({ sessions: [{ session_id: "stale" }], next_cursor: "stale-cursor" }) }));
    expect(result.current.sessions.map((row) => row.session_id)).toEqual(["new"]);
    expect(result.current.nextCursor).toBe("new-cursor");
  });

  // 2026-08-05: this list became CROSS-SKILL. Switching agent via the top bar
  // starts a new session on the new skill, so scoping history to the current
  // skill showed only the fragment for whichever agent the user was standing
  // on, and a sitting spread across two agents read as "it wasn't recorded".
  it("fetches ALL the user's conversations when no filter is set", async () => {
    mockOk([]);

    renderHook(() => useSkillSessions(null));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/proxy/api/sessions",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("narrows to one agent when a filter is set", async () => {
    mockOk([]);

    renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/proxy/api/sessions?skill_id=my-skill",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("returns sessions on success", async () => {
    const session = {
      session_id: "sess-1",
      skill_id: "my-skill",
      owner_uid: "u1",
      title: "Test session",
      turn_count: 2,
      first_message_at: "2026-04-24T10:00:00Z",
      last_message_at: "2026-04-24T10:01:00Z",
      archived_at: null,
      document_ids: [],
      is_owner: true,
    };
    mockOk([session]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].session_id).toBe("sess-1");
    expect(result.current.error).toBeNull();
  });

  it("returns empty list when no sessions", async () => {
    mockOk([]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.sessions).toEqual([]);
  });

  it("sets error on HTTP failure", async () => {
    mockError(500);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe("Failed to load sessions");
  });

  it("a null filter means ALL agents, not 'skip the fetch'", async () => {
    // Was "does not fetch when skillId is null" — that only ever passed by
    // timing (fetchWithAuth awaits a token, so the spy is not called in the
    // same tick). Null now explicitly means the cross-skill list.
    mockOk([]);
    renderHook(() => useSkillSessions(null));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toBe("/api/proxy/api/sessions");
  });

  it("refetches when a sessions-changed event is dispatched (cross-panel sync)", async () => {
    mockOk([{ session_id: "s1" }]);
    mockOk([{ session_id: "s1" }, { session_id: "s2" }]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Another panel deletes (or renames) a session and notifies.
    window.dispatchEvent(new CustomEvent("aitana:sessions-changed"));

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
  });

  it("分页编码游标、阻止并发请求并按 session_id 去重", async () => {
    mockOk([{ session_id: "s1" }], "next /?&");
    let resolvePage!: (value: unknown) => void;
    mockFetch.mockImplementationOnce(() => new Promise((resolve) => { resolvePage = resolve; }));
    const { result } = renderHook(() => useSkillSessions("agent /"));
    await waitFor(() => expect(result.current.nextCursor).toBe("next /?&"));
    act(() => { result.current.loadMore(); result.current.loadMore(); });
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    expect(mockFetch.mock.calls[1][0]).toBe("/api/proxy/api/sessions?skill_id=agent%20%2F&cursor=next%20%2F%3F%26");
    expect(result.current.isLoadingMore).toBe(true);
    await act(async () => resolvePage({ ok: true, json: async () => ({ sessions: [{ session_id: "s1" }, { session_id: "s2" }, { session_id: "s2" }], next_cursor: "next /?&" }) }));
    expect(result.current.sessions.map((row) => row.session_id)).toEqual(["s1", "s2"]);
    expect(result.current.isLoadingMore).toBe(false);
    expect(result.current.nextCursor).toBeNull();
    act(() => result.current.loadMore());
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("翻页失败保留数据和游标，允许同一页重试", async () => {
    mockOk([{ session_id: "s1" }], "page-2");
    mockError();
    mockOk([{ session_id: "s2" }]);
    const { result } = renderHook(() => useSkillSessions(null));
    await waitFor(() => expect(result.current.nextCursor).toBe("page-2"));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.nextCursor).toBe("page-2");
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
    expect(result.current.error).toBeNull();
    expect(result.current.nextCursor).toBeNull();
  });

  it("忽略被新 refetch 替代的结果、错误与 finally", async () => {
    let rejectOld!: (error: Error) => void;
    let resolveNew!: (value: unknown) => void;
    mockFetch.mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject; }));
    mockFetch.mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve; }));
    const { result } = renderHook(() => useSkillSessions(null));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    act(() => result.current.refetch());
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    await act(async () => rejectOld(new Error("stale")));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.error).toBeNull();
    await act(async () => resolveNew({ ok: true, json: async () => ({ sessions: [{ session_id: "new" }], next_cursor: null }) }));
    expect(result.current.sessions[0].session_id).toBe("new");
    expect(result.current.isLoading).toBe(false);
  });

  it("筛选切换后忽略已开始解析的旧响应", async () => {
    let resolveJson!: (value: unknown) => void;
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => new Promise((resolve) => { resolveJson = resolve; }) });
    mockOk([{ session_id: "new" }]);
    const { result, rerender } = renderHook(({ filter }) => useSkillSessions(filter), { initialProps: { filter: "old" } });
    await waitFor(() => expect(resolveJson).toBeTypeOf("function"));
    rerender({ filter: "new" });
    await waitFor(() => expect(result.current.sessions[0]?.session_id).toBe("new"));
    await act(async () => resolveJson({ sessions: [{ session_id: "old" }], next_cursor: "old-cursor" }));
    expect(result.current.sessions[0].session_id).toBe("new");
    expect(result.current.nextCursor).toBeNull();
  });

  it("focus 刷新回第一页，刷新失败不清空已加载数据", async () => {
    mockOk([{ session_id: "s1" }], "p2");
    mockOk([{ session_id: "s2" }]);
    mockError();
    mockOk([{ session_id: "latest" }], "fresh-p2");
    const { result } = renderHook(() => useSkillSessions(null));
    await waitFor(() => expect(result.current.nextCursor).toBe("p2"));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
    act(() => window.dispatchEvent(new Event("focus")));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.sessions).toHaveLength(2);
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.sessions[0]?.session_id).toBe("latest"));
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.nextCursor).toBe("fresh-p2");
    expect(mockFetch.mock.calls[2][0]).toBe("/api/proxy/api/sessions");
  });

  it("refetch 替代在途翻页，旧页晚到不能追加或修改新游标", async () => {
    mockOk([{ session_id: "s1" }], "old-p2");
    let resolvePage!: (value: unknown) => void;
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => new Promise((resolve) => { resolvePage = resolve; }) });
    mockOk([{ session_id: "fresh" }], "new-p2");
    const { result } = renderHook(() => useSkillSessions(null));
    await waitFor(() => expect(result.current.nextCursor).toBe("old-p2"));
    act(() => result.current.loadMore());
    await waitFor(() => expect(resolvePage).toBeTypeOf("function"));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.sessions[0]?.session_id).toBe("fresh"));
    await act(async () => resolvePage({ sessions: [{ session_id: "stale-page" }], next_cursor: "old-p3" }));
    expect(result.current.sessions.map((row) => row.session_id)).toEqual(["fresh"]);
    expect(result.current.nextCursor).toBe("new-p2");
    expect(result.current.isLoadingMore).toBe(false);
  });

  it("卸载取消请求，即使 fetch 忽略 abort 也不继续解析", async () => {
    let resolveOld!: (value: unknown) => void;
    const json = vi.fn();
    mockFetch.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const { unmount } = renderHook(() => useSkillSessions(null));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const signal = mockFetch.mock.calls[0][1].signal as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => resolveOld({ ok: true, json }));
    expect(json).not.toHaveBeenCalled();
  });
});
