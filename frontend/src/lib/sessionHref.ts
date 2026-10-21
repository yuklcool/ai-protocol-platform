import type { ChatSessionSummary } from "@/hooks/useSkillSessions";

/** owner_uid 是会话所有者，不用于推断技能路由。 */
export function sessionHref(summary: Pick<ChatSessionSummary, "skill_id" | "session_id">): string {
  return `/chat/${encodeURIComponent(summary.skill_id)}?session=${encodeURIComponent(summary.session_id)}`;
}
