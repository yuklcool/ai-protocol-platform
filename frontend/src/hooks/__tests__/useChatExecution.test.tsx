import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useChatExecution } from "../useChatExecution";

const fake = vi.hoisted(() => ({
  threadId: "session-1",
  messages: [{ id: "user-1", role: "user", content: "Analyze" }],
  subscriber: {} as Record<string, (payload: unknown) => void>,
  unsubscribe: vi.fn(),
  subscribe: vi.fn(),
}));
vi.mock("@/providers/AGUIProvider", () => ({ useAGUIAgent: () => fake }));

function emit(name: string, event: Record<string, unknown> = {}) {
  act(() => fake.subscriber[name]?.({ event }));
}

describe("shared chat execution stream", () => {
  beforeEach(() => {
    fake.unsubscribe.mockClear();
    fake.messages = [{ id: "user-1", role: "user", content: "Analyze" }];
    fake.subscribe.mockImplementation((subscriber: typeof fake.subscriber) => {
      fake.subscriber = subscriber;
      return { unsubscribe: fake.unsubscribe };
    });
  });

  it("updates one run card and waits for a tool RESULT, not the end of arguments", () => {
    const { result } = renderHook(() => useChatExecution("user-a"));
    emit("onRunStartedEvent", { runId: "run-1" });
    emit("onToolCallStartEvent", { toolCallId: "tool-1", toolCallName: "read_document" });
    emit("onToolCallEndEvent", { toolCallId: "tool-1" });
    expect(result.current.executions[0]).toMatchObject({ afterMessageId: "user-1", status: "running", tools: [{ status: "running" }] });
    emit("onToolCallResultEvent", { toolCallId: "tool-1", content: "ok" });
    emit("onRunFinishedEvent");
    emit("onRunFinalized");
    expect(result.current.executions).toHaveLength(1);
    expect(result.current.executions[0]).toMatchObject({ status: "completed", tools: [{ status: "success" }] });
  });

  it("anchors an action continuation to the preceding assistant message", () => {
    fake.messages = [{ id: "card-intro", role: "assistant", content: "Please confirm" }];
    const { result } = renderHook(() => useChatExecution("user-a"));
    emit("onRunStartedEvent", { runId: "action-run" });
    expect(result.current.executions[0].afterMessageId).toBe("card-intro");
  });

  it("does not claim completion on a truncated stream or a rejected run", () => {
    const { result } = renderHook(() => useChatExecution("user-a"));
    emit("onRunStartedEvent", { runId: "r1" });
    emit("onRunFinalized");
    expect(result.current.executions[0].status).toBe("interrupted");
    emit("onRunStartedEvent", { runId: "r2" });
    emit("onRunErrorEvent", { message: "denied" });
    emit("onRunFinalized");
    expect(result.current.executions[1].status).toBe("failed");
  });

  it("preserves a user stop through stream finalization", () => {
    const { result } = renderHook(() => useChatExecution("user-a"));
    emit("onRunStartedEvent", { runId: "r1" });
    act(() => result.current.markStopped());
    emit("onRunFinalized");
    expect(result.current.executions[0].status).toBe("cancelled");
  });

  it("clears activity when the identity changes and ignores the old subscription", () => {
    const { result, rerender } = renderHook(({ uid }) => useChatExecution(uid), { initialProps: { uid: "a" } });
    emit("onRunStartedEvent", { runId: "private-run" });
    const old = fake.subscriber;
    rerender({ uid: "b" });
    expect(result.current.executions).toEqual([]);
    act(() => old.onRunStartedEvent?.({ event: { runId: "late-private-run" } }));
    act(() => old.onToolCallStartEvent?.({ event: { toolCallId: "old", toolCallName: "private" } }));
    expect(result.current.executions).toEqual([]);
    expect(fake.unsubscribe).toHaveBeenCalled();
  });
});
