import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StudioDraft } from "@/components/studio/applyProposal";
import { StudioBuilderForm } from "@/components/studio/StudioBuilderForm";

const fetchWithAuthMock = vi.fn();
vi.mock("@/lib/apiClient", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

const initialDraft: StudioDraft = {
  name: "",
  displayName: "",
  description: "",
  instructions: "",
  skillMetadata: { model: "smart", tools: [], subSkills: [], toolConfigs: {} },
  persona: { interactionStyle: "concise", voice: {} },
  welcome: {},
  accessControl: { type: "private" },
};

function reply(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: async () => body });
}

function Harness() {
  const [draft, setDraft] = useState<StudioDraft>(initialDraft);
  return <StudioBuilderForm draft={draft} setDraft={setDraft} isNew />;
}

describe("StudioBuilderForm", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation((url: unknown) => {
      const path = String(url);
      if (path.endsWith("/api/voice/voices")) return reply({ languages: [], voices: {} });
      if (path.endsWith("/api/models")) return reply({ models: [], tier_defaults: {} });
      if (path.endsWith("/api/tools")) return reply({ tools: [] });
      if (path.endsWith("/api/skills")) return reply([]);
      return reply({});
    });
  });

  it("keeps the English fallback contract and edits the shared draft", () => {
    render(<Harness />);

    const displayName = screen.getByLabelText("Display name") as HTMLInputElement;
    fireEvent.change(displayName, { target: { value: "Lighting Analyst" } });
    expect(displayName.value).toBe("Lighting Analyst");

    expect(screen.getByText("Persona")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Concise" })).toBeInTheDocument();
  });

  it("uses a generic tenant-safe document path example", () => {
    render(<Harness />);
    expect(screen.getByPlaceholderText("documents/PPAs/longform/")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/aitana/i)).not.toBeInTheDocument();
  });
});
