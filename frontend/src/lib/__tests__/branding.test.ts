import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ALL_BRAND_VARS = [
  "NEXT_PUBLIC_BRAND_APP_NAME",
  "NEXT_PUBLIC_BRAND_TAGLINE",
  "NEXT_PUBLIC_BRAND_DESCRIPTION",
  "NEXT_PUBLIC_BRAND_FAVICON",
  "NEXT_PUBLIC_BRAND_LOGO_HERO",
  "NEXT_PUBLIC_BRAND_LOGO_AVATAR",
  "NEXT_PUBLIC_BRAND_EMAIL",
  "NEXT_PUBLIC_BRAND_GITHUB",
  "NEXT_PUBLIC_BRAND_PRIMARY_HSL",
  "NEXT_PUBLIC_BRAND_PRIMARY_FOREGROUND_HSL",
  "NEXT_PUBLIC_BRAND_DEMO_HERO_EYEBROW",
  "NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_A",
  "NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_B",
  "NEXT_PUBLIC_BRAND_DEMO_HERO_BODY",
  "NEXT_PUBLIC_BRAND_DEMO_CTA_PRIMARY",
  "NEXT_PUBLIC_BRAND_DEMO_CTA_SECONDARY",
  "NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF",
  "NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF_SECONDARY",
  "NEXT_PUBLIC_BRAND_DEMO_TECH_HREF",
] as const;

function clearAllBrandVars() {
  for (const variable of ALL_BRAND_VARS) vi.stubEnv(variable, "");
}

async function freshModule() {
  vi.resetModules();
  return import("@/lib/branding");
}

describe("BRANDING — configurable fork display identity", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses neutral AI Protocol Platform defaults when overrides are absent", async () => {
    clearAllBrandVars();
    const { BRANDING, CITATION_SCHEME } = await freshModule();
    expect(BRANDING.appName).toBe("AI Protocol Platform");
    expect(BRANDING.tagline).toBe("Open Agent Protocol Platform");
    expect(BRANDING.logo.favicon).toBe("/images/logo/platform-mark.svg");
    expect(BRANDING.logo.heroAnimated).toBe("/images/logo/platform-mark.svg");
    expect(BRANDING.logo.chatAvatar).toBe("/images/logo/platform-mark.svg");
    expect(BRANDING.contact.email).toBe("");
    expect(BRANDING.contact.githubRepo).toBe(
      "https://github.com/yuklcool/ai-protocol-platform",
    );
    expect(BRANDING.theme.primaryHsl).toBe("199 89% 48%");
    expect(CITATION_SCHEME).toBe("aip");
  });

  it("uses NEXT_PUBLIC_BRAND_* overrides field by field", async () => {
    clearAllBrandVars();
    vi.stubEnv("NEXT_PUBLIC_BRAND_APP_NAME", "Acme Energy");
    vi.stubEnv("NEXT_PUBLIC_BRAND_TAGLINE", "PPA & PtX intelligence");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DESCRIPTION", "Energy advisory platform");
    vi.stubEnv("NEXT_PUBLIC_BRAND_FAVICON", "/brand/favicon.svg");
    vi.stubEnv("NEXT_PUBLIC_BRAND_LOGO_HERO", "/brand/hero.svg");
    vi.stubEnv("NEXT_PUBLIC_BRAND_LOGO_AVATAR", "/brand/avatar.svg");
    vi.stubEnv("NEXT_PUBLIC_BRAND_EMAIL", "hello@example.com");
    vi.stubEnv("NEXT_PUBLIC_BRAND_GITHUB", "https://github.com/example/acme");
    vi.stubEnv("NEXT_PUBLIC_BRAND_PRIMARY_HSL", "220 80% 50%");
    vi.stubEnv("NEXT_PUBLIC_BRAND_PRIMARY_FOREGROUND_HSL", "0 0% 100%");

    const { BRANDING } = await freshModule();
    expect(BRANDING.appName).toBe("Acme Energy");
    expect(BRANDING.tagline).toBe("PPA & PtX intelligence");
    expect(BRANDING.description).toBe("Energy advisory platform");
    expect(BRANDING.logo).toEqual({
      favicon: "/brand/favicon.svg",
      heroAnimated: "/brand/hero.svg",
      chatAvatar: "/brand/avatar.svg",
    });
    expect(BRANDING.contact).toEqual({
      email: "hello@example.com",
      githubRepo: "https://github.com/example/acme",
    });
    expect(BRANDING.theme).toEqual({
      primaryHsl: "220 80% 50%",
      primaryForegroundHsl: "0 0% 100%",
    });
  });

  it("treats empty NEXT_PUBLIC brand variables as unset", async () => {
    clearAllBrandVars();
    const { BRANDING } = await freshModule();
    expect(BRANDING.appName).toBe("AI Protocol Platform");
    expect(BRANDING.tagline).toBe("Open Agent Protocol Platform");
    expect(BRANDING.logo.favicon).toBe("/images/logo/platform-mark.svg");
  });

  it("keeps deployment hero-copy overrides optional", async () => {
    clearAllBrandVars();
    const { BRAND_COPY_OVERRIDES, BRANDING } = await freshModule();
    expect(BRAND_COPY_OVERRIDES.heroEyebrow).toBe("");
    expect(BRAND_COPY_OVERRIDES.heroLineA).toBe("");
    // Backwards-compatible BRANDING.demo remains usable by components not yet
    // migrated to the locale dictionary.
    expect(BRANDING.demo.heroEyebrow).toBe("Open agent platform");
    expect(BRANDING.demo.heroLineA).toBe("Build AI agents");
    expect(BRANDING.demo.ctaPrimary).toBe("Open the assistant");
    expect(BRANDING.demo.pillars).toHaveLength(6);
  });

  it("honours explicit hero copy and CTA overrides", async () => {
    clearAllBrandVars();
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_HERO_EYEBROW", "Energy intelligence");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_A", "Side-by-side");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_B", "PPA comparison");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_HERO_BODY", "Compare contracts.");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_CTA_PRIMARY", "Ask the expert");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_CTA_SECONDARY", "Compare contracts");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF", "/chat/expert");
    vi.stubEnv("NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF_SECONDARY", "/chat/compare");

    const { BRAND_COPY_OVERRIDES, BRANDING } = await freshModule();
    expect(BRAND_COPY_OVERRIDES.heroEyebrow).toBe("Energy intelligence");
    expect(BRANDING.demo.heroLineA).toBe("Side-by-side");
    expect(BRANDING.demo.heroLineB).toBe("PPA comparison");
    expect(BRANDING.demo.heroBody).toBe("Compare contracts.");
    expect(BRANDING.demo.ctaPrimary).toBe("Ask the expert");
    expect(BRANDING.demo.ctaSecondary).toBe("Compare contracts");
    expect(BRANDING.demo.chatHref).toBe("/chat/expert");
    expect(BRANDING.demo.chatHrefSecondary).toBe("/chat/compare");
  });

  it("resolves safe tenant display overrides without replacing contacts or demo policy", async () => {
    clearAllBrandVars();
    const { BRANDING, resolveBranding } = await freshModule();
    const resolved = resolveBranding({
      appName: "Tenant Portal",
      logo: { chatAvatar: "/tenant/avatar.svg" },
      theme: { primaryHsl: "180 70% 40%" },
    });

    expect(resolved.appName).toBe("Tenant Portal");
    expect(resolved.logo.favicon).toBe(BRANDING.logo.favicon);
    expect(resolved.logo.chatAvatar).toBe("/tenant/avatar.svg");
    expect(resolved.theme.primaryHsl).toBe("180 70% 40%");
    expect(resolved.contact).toEqual(BRANDING.contact);
    expect(resolved.demo).toEqual(BRANDING.demo);
  });
});
