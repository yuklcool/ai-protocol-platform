"use client";

import { type ReactNode } from "react";
import type { User } from "@/lib/firebase";
import { useUserSkills } from "@/hooks/useUserSkills";
import { useTenantDefaultSkill } from "@/hooks/useTenantDefaultSkill";
import { RootAgentBar } from "@/components/navigation/RootAgentBar";

export interface ShellChromeProps {
  skillId: string;
  user: User;
  children: ReactNode;
}

/**
 * v6.6.0 — global chrome shared by every shell mode.
 *
 * The product is a Single Root Agent. Skills remain runtime capabilities, so
 * the chat chrome must never present a SkillSwitcher or make users choose an
 * Agent-as-Skill. The current skill id is retained only for compatibility with
 * the legacy streaming route and session URL.
 */
export function ShellChrome({ skillId, user, children }: ShellChromeProps) {
  const { skills } = useUserSkills(user.uid);
  const defaultSkillId = useTenantDefaultSkill(skills);
  const defaultSkill = skills.find((s) => s.skillId === defaultSkillId);

  return (
    // `h-full`, not `h-screen` (v6.19.0, AIPLA #23). Claiming 100vh here is
    // wrong whenever anything else occupies vertical space in the root layout —
    // a banner above us is additive, and the bottom of this shell (the chat
    // input) ends up below the fold. `h-full` fills whatever the layout's
    // `flex-1 min-h-0` wrapper actually grants us; `min-h-0` lets us shrink
    // below content height so the inner scroll regions do the scrolling.
    <div className="flex h-full min-h-0 flex-col">
      <RootAgentBar
        skills={skills}
        defaultSkill={defaultSkill}
        currentSkillId={skillId}
        // New chat opens a FRESH session, NEVER resuming. Route straight to a
        // skill with NO ?session= so useStableThreadId mints a new thread
        // (X → null → fresh). Prefer the tenant DEFAULT skill (the front door —
        // ONE Assistant); if it isn't configured/resolved yet, fall back to a
        // fresh session of the CURRENT skill (always known), then the first
        // enabled skill — anything but "/", which useLandingTarget would RESUME
        // the most-recent session on (the bug: a tenant with no default_skill
        // had New chat bounce back to the last thread). 2026-07-16.
      />
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
