import { describe, expect, it } from "vitest";
import { sessionHref } from "@/lib/sessionHref";

describe("sessionHref", () => {
  it("使用 row 的 skill_id 和 session_id，而不是 owner_uid", () => {
    const row = { skill_id: "actual-agent", session_id: "s1", owner_uid: "session-owner" };
    expect(sessionHref(row)).toBe("/chat/actual-agent?session=s1");
  });

  it("安全编码路径和 query，不能注入额外路由参数", () => {
    const row = { skill_id: "@owner/技能 ?#%", session_id: "s/1 ?&next=/admin#%" };
    const href = sessionHref(row);
    expect(href).toBe(`/chat/${encodeURIComponent(row.skill_id)}?session=${encodeURIComponent(row.session_id)}`);
    const url = new URL(href, "https://example.test");
    expect([...url.searchParams.keys()]).toEqual(["session"]);
    expect(url.searchParams.get("session")).toBe(row.session_id);
    expect(url.hash).toBe("");
  });
});
