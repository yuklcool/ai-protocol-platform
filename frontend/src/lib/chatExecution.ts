import type { SkillMessage, ToolCallState } from "@/hooks/useSkillAgent";

export type ExecutionStatus = "running" | "completed" | "failed" | "cancelled" | "interrupted" | "recorded";

/** Transport activity, never an inferred business plan or hidden reasoning. */
export interface ChatExecution {
  id: string;
  afterMessageId: string | null;
  startedAt: number;
  status: ExecutionStatus;
  stage?: string;
  tools: ToolCallState[];
}

/** Reconstruct only recorded calls. History cannot prove a Run finished. */
export function recordedExecutions(
  messages: SkillMessage[],
  calls: ToolCallState[],
  live: ChatExecution[],
): ChatExecution[] {
  const liveIds = new Set(live.flatMap((run) => run.tools.map((tool) => tool.id)));
  const groups = new Map<string, ChatExecution>();
  const seen = new Set<string>();
  for (const call of [...calls].sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0))) {
    if (liveIds.has(call.id) || seen.has(call.id)) continue;
    seen.add(call.id);
    // Only use persisted timestamps; never attach an old tool to the latest
    // live reply merely because its source message was not in /messages.
    const anchor = call.ts ? messages.filter((m) => m.role === "user" && m.createdAt !== undefined && m.createdAt <= call.ts!).at(-1) : undefined;
    const key = anchor?.id ?? "unanchored";
    const group = groups.get(key) ?? {
      id: `history:${key}`,
      afterMessageId: anchor?.id ?? null,
      startedAt: call.ts ?? 0,
      status: "recorded" as const,
      tools: [],
    };
    group.tools.push(call);
    groups.set(key, group);
  }
  return [...groups.values()];
}
