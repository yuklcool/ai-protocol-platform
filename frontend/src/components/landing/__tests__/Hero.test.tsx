import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BRANDING } from "@/lib/branding";
import { translate } from "@/lib/i18n";
import { Hero } from "../Hero";

describe("Hero", () => {
  it("renders English locale defaults when isolated outside the app provider", () => {
    render(<Hero />);
    expect(screen.getByText(translate("en", "home.hero.eyebrow"))).toBeInTheDocument();
    expect(screen.getByText(translate("en", "home.hero.lineA"))).toBeInTheDocument();
    expect(screen.getByText(translate("en", "home.hero.lineB"))).toBeInTheDocument();
    expect(screen.getByText(translate("en", "home.hero.body"))).toBeInTheDocument();
  });

  it("renders both localized CTAs with deployment-configured hrefs", () => {
    render(<Hero />);
    const primary = screen.getByRole("link", {
      name: new RegExp(translate("en", "home.hero.ctaPrimary"), "i"),
    });
    expect(primary).toHaveAttribute("href", BRANDING.demo.chatHref);

    const secondary = screen.getByRole("link", {
      name: new RegExp(translate("en", "home.hero.ctaSecondary"), "i"),
    });
    expect(secondary).toHaveAttribute("href", BRANDING.demo.chatHrefSecondary);
  });

  it("renders a right-column visual when the visual prop is provided", () => {
    render(
      <Hero visual={<div data-testid="custom-visual">visual content</div>} />,
    );
    expect(screen.getByTestId("custom-visual")).toBeInTheDocument();
  });

  it("uses single-column layout when no visual prop is provided", () => {
    const { container } = render(<Hero />);
    const layout = container.querySelector("section > div");
    expect(layout?.className).toContain("flex-col");
  });
});
