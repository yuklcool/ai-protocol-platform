import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { A2UIConfigEditor } from "../A2UIConfigEditor";
import type { StudioDraft } from "../applyProposal";

function Harness({ config = {} }: { config?: Record<string, unknown> }) {
  const [draft, setDraft] = useState<StudioDraft>({
    skillMetadata: { model: "smart", tools: [], subSkills: [], toolConfigs: {
      mcp: { servers: ["lighting"] }, a2ui: config,
    } },
  });
  return <><A2UIConfigEditor draft={draft} setDraft={setDraft} /><output data-testid="draft">{JSON.stringify(draft)}</output></>;
}

const saved = () => JSON.parse(screen.getByTestId("draft").textContent!).skillMetadata.toolConfigs;

describe("A2UIConfigEditor", () => {
  it("uses runtime-compatible defaults without mutating the loaded config", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Enable interactive UI")).toBeChecked();
    expect(screen.getByLabelText("Share interface data and actions with the agent")).not.toBeChecked();
    expect(screen.getByRole("option", { name: "Update existing data" })).toBeDisabled();
    expect(saved().a2ui).toEqual({});
  });

  it("resets patch when switching to chat and preserves unrelated configuration", () => {
    render(<Harness config={{ default_surface: "workspace", default_update_mode: "patch", allow_surface_context_writes: true }} />);
    fireEvent.change(screen.getByLabelText("Display area"), { target: { value: "chat" } });
    expect(saved()).toEqual({ mcp: { servers: ["lighting"] }, a2ui: {
      default_surface: "chat", default_update_mode: "replace", allow_surface_context_writes: true,
    } });
    fireEvent.change(screen.getByLabelText("Display area"), { target: { value: "workspace" } });
    fireEvent.change(screen.getByLabelText("Update mode"), { target: { value: "patch" } });
    expect(saved().a2ui.default_update_mode).toBe("patch");
  });

  it("preserves custom surfaces and keeps action grants independent", () => {
    render(<Harness config={{ default_surface: "custom:grid", default_update_mode: "patch" }} />);
    expect(screen.getByLabelText("Display area")).toHaveValue("custom:grid");
    fireEvent.click(screen.getByLabelText("Allow interface actions to start an agent response"));
    expect(saved().a2ui.allow_action_triggered_runs).toBe(true);
    expect(saved().a2ui.allow_surface_context_writes).toBeUndefined();
    fireEvent.click(screen.getByLabelText("Enable interactive UI"));
    expect(screen.getByLabelText("Display area")).toBeDisabled();
    expect(saved().a2ui.default_surface).toBe("custom:grid");
  });

  it("normalizes legacy disabled chat patch configurations when enabled", () => {
    render(<Harness config={{ enabled: false, default_update_mode: "patch" }} />);
    fireEvent.click(screen.getByLabelText("Enable interactive UI"));
    expect(saved().a2ui).toEqual({ enabled: true, default_update_mode: "replace" });
  });
});
