"use client";

export type LandingTarget =
  | { kind: "loading" }
  | { kind: "chat"; href: "/chat/root-agent" };

/** 登录后的入口不依赖会话历史或后端可用性。 */
export function useLandingTarget(enabled: boolean): LandingTarget {
  return enabled ? { kind: "chat", href: "/chat/root-agent" } : { kind: "loading" };
}
