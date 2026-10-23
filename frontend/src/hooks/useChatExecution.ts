"use client";

import { useCallback, useEffect, useState } from "react";
import { useAGUIAgent } from "@/providers/AGUIProvider";
import type { ChatExecution, ExecutionStatus } from "@/lib/chatExecution";

/** Observe the SAME HttpAgent for text turns and authorized A2UI action turns.
 * TOOL_CALL_END only closes streamed arguments; a result proves tool return.
 * No request, second runtime, retry, private reasoning or local persistence.
 */
export function useChatExecution(identity: string) {
  const agent = useAGUIAgent();
  const scope = `${identity}:${agent?.threadId ?? ""}`;
  const [snapshot, setSnapshot] = useState<{ scope: string; runs: ChatExecution[] }>({ scope, runs: [] });

  useEffect(() => {
    if (!agent?.subscribe) return;
    let active: string | null = null;
    let terminal = false;
    let disposed = false;
    setSnapshot((previous) => previous.scope === scope ? previous : { scope, runs: [] });
    const update = (fn: (run: ChatExecution) => ChatExecution) => {
      const id = active;
      if (!id || disposed) return;
      setSnapshot((previous) => previous.scope === scope
        ? { scope, runs: previous.runs.map((run) => run.id === id ? fn(run) : run) }
        : previous);
    };
    const settle = (status: ExecutionStatus) => {
      terminal = true;
      update((run) => run.status === "cancelled" && status === "interrupted" ? run : ({ ...run, status, stage: undefined }));
    };
    const subscription = agent.subscribe({
      onRunStartedEvent: ({ event }) => {
        if (disposed) return;
        active = event.runId;
        terminal = false;
        // The last visible message is the user request, or the card's
        // preceding assistant message for an action-triggered continuation.
        const anchor = [...agent.messages].reverse().find((m) => (m.role === "user" || m.role === "assistant") && typeof m.content === "string");
        const run: ChatExecution = { id: event.runId, afterMessageId: anchor?.id ?? null, startedAt: Date.now(), status: "running", tools: [] };
        setSnapshot((previous) => ({ scope, runs: [...(previous.scope === scope ? previous.runs.filter((r) => r.id !== run.id) : []), run] }));
      },
      onCustomEvent: ({ event }) => {
        if (event.name !== "STAGE_PROGRESS" || !event.value || typeof event.value.label !== "string") return;
        update((run) => ({ ...run, stage: event.value.label.slice(0, 240) }));
      },
      onToolCallStartEvent: ({ event }) => update((run) => ({
        ...run,
        tools: [...run.tools.filter((t) => t.id !== event.toolCallId), { id: event.toolCallId, name: event.toolCallName, status: "running", ts: Date.now() }],
      })),
      onToolCallResultEvent: ({ event }) => update((run) => ({
        ...run,
        tools: run.tools.map((t) => t.id === event.toolCallId ? { ...t, status: "success" } : t),
      })),
      onRunFinishedEvent: () => settle("completed"),
      onRunErrorEvent: () => settle("failed"),
      onRunFailed: () => settle("failed"),
      onRunFinalized: () => { if (!terminal) settle("interrupted"); },
    });
    return () => { disposed = true; subscription.unsubscribe(); };
  }, [agent, scope]);

  const cancel = useCallback(() => {
    // Record only the local stop request, never claim server rollback.
    setSnapshot((previous) => ({ ...previous, runs: previous.runs.map((run) => run.status === "running" ? { ...run, status: "cancelled", stage: undefined } : run) }));
  }, []);
  return { executions: snapshot.scope === scope ? snapshot.runs : [], markStopped: cancel };
}
