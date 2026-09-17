import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ContextBanner } from "@/components/chat/ContextBanner";
import { DelegationMarker } from "@/components/chat/DelegationMarker";
import { FallbackNotice } from "@/components/chat/FallbackNotice";

describe("Chat core localized labels", () => {
  it("keeps the document-context English fallback contract", () => {
    render(<ContextBanner context={{ folderName: "Contracts", docCount: 1 }} />);
    expect(screen.getByText("Analyzing 1 document from Contracts")).toBeInTheDocument();
  });

  it("keeps fallback transparency and model ids visible", () => {
    render(
      <FallbackNotice
        fromModel="anthropic/claude-primary"
        toModel="openai/gpt-backup"
        reason="provider_cooldown"
      />,
    );
    expect(screen.getByText("claude-primary")).toBeInTheDocument();
    expect(screen.getByText("gpt-backup")).toBeInTheDocument();
    expect(screen.getByText(/answered by backup/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveAttribute(
      "aria-label",
      "Backup model gpt-backup answered because claude-primary was unavailable",
    );
  });

  it("keeps delegation target names intact", () => {
    render(<DelegationMarker targetDisplay="Lighting Analyst" mode="auto" />);
    expect(screen.getByText("Lighting Analyst")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveAttribute(
      "aria-label",
      "Delegated to Lighting Analyst",
    );
  });
});
