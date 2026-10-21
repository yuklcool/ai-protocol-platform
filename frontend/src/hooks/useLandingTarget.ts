"use client";

export type LandingTarget =
  | { kind: "loading" }
  | { kind: "workspace"; href: "/workspace" };

/** 登录后的入口不依赖会话历史或后端可用性。 */
export function useLandingTarget(enabled: boolean): LandingTarget {
  return enabled ? { kind: "workspace", href: "/workspace" } : { kind: "loading" };
}
