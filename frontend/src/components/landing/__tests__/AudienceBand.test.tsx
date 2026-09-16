import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BRANDING } from "@/lib/branding";
import { AudienceBand } from "../AudienceBand";

describe("AudienceBand", () => {
  it("renders the platform-team section heading", () => {
    render(<AudienceBand />);
    expect(
      screen.getByText(/built for teams operating ai agents/i),
    ).toBeInTheDocument();
  });

  it("renders all three platform audience roles", () => {
    render(<AudienceBand />);
    expect(screen.getByText(/platform operators/i)).toBeInTheDocument();
    expect(screen.getByText(/agent builders/i)).toBeInTheDocument();
    expect(screen.getByText(/protocol engineers/i)).toBeInTheDocument();
  });

  it("interpolates the product name from BRANDING into the engineer column", () => {
    render(<AudienceBand />);
    expect(
      screen.getByText(new RegExp(`Extend ${BRANDING.appName}`, "i")),
    ).toBeInTheDocument();
  });
});
