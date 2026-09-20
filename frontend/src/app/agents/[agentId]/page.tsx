"use client";

import { redirect } from "next/navigation";

/**
 * Legacy multi-Agent URL. Issue #74 now defines one Root Agent, so old
 * bookmarks land on the single settings surface while `/skills/studio/*`
 * remains the explicit compatibility editor for Skills.
 */
export default function AgentPage() {
  redirect("/agent");
}
