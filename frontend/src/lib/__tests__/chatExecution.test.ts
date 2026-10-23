import { describe, expect, it } from "vitest";
import { recordedExecutions, type ChatExecution } from "../chatExecution";
import type { SkillMessage, ToolCallState } from "@/hooks/useSkillAgent";

const messages: SkillMessage[] = [
  { id: "u1", role: "user", content: "one", createdAt: 100 },
  { id: "a1", role: "assistant", content: "first result", createdAt: 300 },
  { id: "u2", role: "user", content: "two", createdAt: 400 },
];
describe("recorded execution anchoring", () => {
  it("keeps earlier calls under their original user turn and deduplicates live calls", () => {
    const calls: ToolCallState[] = [
      { id: "c2", name: "second", ts: 500, status: "success" },
      { id: "c1", name: "first", ts: 200, status: "success" },
      { id: "c1", name: "first", ts: 200, status: "success" },
    ];
    const live: ChatExecution[] = [{ id: "r2", afterMessageId: "u2", startedAt: 450, status: "completed", tools: [calls[0]] }];
    expect(recordedExecutions(messages, calls, live)).toMatchObject([{ afterMessageId: "u1", status: "recorded", tools: [{ id: "c1" }] }]);
    expect(recordedExecutions(messages, calls, live)[0].tools).toHaveLength(1);
  });
  it("does not invent a run or attach calls with no timestamp to the latest reply", () => {
    const records = recordedExecutions(messages, [{ id: "old", name: "unknown", status: "error" }], []);
    expect(records[0]).toMatchObject({ afterMessageId: null, status: "recorded" });
  });
});
