"use client";

import { use } from "react";
import StudioPage from "@/app/skills/studio/[skillId]/page";

/**
 * Agent-first URL for the existing SkillConfig-backed Studio. Keeping the
 * adapter deliberately thin lets old `/skills/studio/*` bookmarks continue
 * to work while the product-facing route becomes `/agents/*`.
 */
export default function AgentPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = use(params);
  return <StudioPage params={Promise.resolve({ skillId: agentId })} />;
}

