import { describe, expect, it } from "vitest";
import { normalizeRootAgentConfig } from "@/types/rootAgent";

describe("Root Agent config compatibility", () => {
  it("supplies a single-agent default for legacy platform config", () => {
    const config = normalizeRootAgentConfig(undefined);
    expect(config.displayName).toBe("Root Agent");
    expect(config.interaction.a2uiEnabled).toBe(true);
    expect(config.skills).toEqual([]);
  });

  it("normalizes resource ids and preserves agent-level interaction", () => {
    const config = normalizeRootAgentConfig({
      displayName: "Lighting Assistant",
      skills: ["alarm", 7],
      mcpServers: ["lighting-mcp"],
      interaction: { defaultSurface: "workspace", allowActionTriggeredRuns: true },
    });
    expect(config.displayName).toBe("Lighting Assistant");
    expect(config.skills).toEqual(["alarm", "7"]);
    expect(config.interaction.defaultSurface).toBe("workspace");
    expect(config.interaction.allowActionTriggeredRuns).toBe(true);
    expect(config.interaction.defaultUpdateMode).toBe("replace");
  });
});
