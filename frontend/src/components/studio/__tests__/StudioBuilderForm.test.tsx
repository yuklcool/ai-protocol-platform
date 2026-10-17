import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { StudioBuilderForm } from "../StudioBuilderForm";
import { emptyDraft } from "../draft";

function Harness() {
  const [draft, setDraft] = useState(emptyDraft());
  return <StudioBuilderForm draft={draft} setDraft={setDraft} isNew />;
}

describe("Skill content editor", () => {
  it("edits capability content and sends Agent configuration to the Root settings", () => {
    render(<Harness />);
    const name = screen.getByLabelText("Display name");
    fireEvent.change(name, { target: { value: "Data Analysis" } });
    expect(name).toHaveValue("Data Analysis");
    expect(screen.getByLabelText("Instructions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Root Agent settings" })).toHaveAttribute("href", "/agent");
    expect(screen.queryByText("Persona")).not.toBeInTheDocument();
    expect(screen.queryByText("Model tier")).not.toBeInTheDocument();
  });

  it("adds and removes supporting files", () => {
    render(<Harness />);
    fireEvent.click(screen.getAllByRole("button", { name: "Add file", hidden: true })[0]);
    fireEvent.change(screen.getByLabelText("References · Filename"), { target: { value: "guide.md" } });
    fireEvent.change(screen.getByLabelText("Content"), { target: { value: "Use this reference." } });
    expect(screen.getByLabelText("Content")).toHaveValue("Use this reference.");
    fireEvent.click(screen.getByText("Remove file"));
    expect(screen.queryByLabelText("Content")).not.toBeInTheDocument();
  });
});
