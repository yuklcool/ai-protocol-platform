import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Proposal } from "@/components/studio/applyProposal";

const assistantContent = [
  "Sure — here's a proposal:",
  "```json",
  JSON.stringify({
    proposals: [
      { kind: "set_display_name", label: "Name it Reviewer", value: "Reviewer" },
    ],
  }),
  "```",
].join("\n");

const sendMessage = vi.fn(async () => {});

vi.mock("@/hooks/useSkillAgent", () => ({
  useSkillAgent: () => ({
    sessionId: "copilot-thread-1",
    messages: [
      { id: "u1", role: "user", content: "make a contract reviewer" },
      { id: "a1", role: "assistant", content: assistantContent },
    ],
    toolCalls: [],
    thinkingContent: "",
    isThinking: false,
    stageLabel: null,
    delegations: [],
    sendMessage,
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    stop: vi.fn(),
  }),
}));

import { AuthoringCopilot } from "@/components/studio/AuthoringCopilot";

describe("AuthoringCopilot", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchSpy);
  });

  it("keeps the existing English fallback contract outside an I18nProvider", () => {
    render(<AuthoringCopilot skillId="skill-123" onApplyProposal={vi.fn()} />);
    expect(screen.getByText("Authoring copilot")).toBeInTheDocument();
    expect(screen.getByLabelText("Message the authoring copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("renders a proposal card from an assistant proposals block", () => {
    render(<AuthoringCopilot skillId="skill-123" onApplyProposal={vi.fn()} />);
    expect(screen.getByText("Name it Reviewer")).toBeInTheDocument();
    expect(screen.getByTestId("proposal-card")).toBeInTheDocument();
  });

  it("Apply calls onApplyProposal with the parsed proposal and does NOT fetch", () => {
    const onApply = vi.fn((_p: Proposal) => {});
    render(<AuthoringCopilot skillId="skill-123" onApplyProposal={onApply} />);

    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "set_display_name", value: "Reviewer" }),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("Dismiss removes the card", () => {
    render(<AuthoringCopilot skillId="skill-123" onApplyProposal={vi.fn()} />);
    expect(screen.getByTestId("proposal-card")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));

    expect(screen.queryByTestId("proposal-card")).not.toBeInTheDocument();
  });
});
