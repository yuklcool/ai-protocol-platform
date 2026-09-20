/**
 * Deployment branding configuration.
 *
 * Keep product identity here instead of scattering fork names through protocol
 * or business components. Runtime protocol identifiers remain independent from
 * the display brand.
 */

export const CITATION_SCHEME =
  process.env.NEXT_PUBLIC_CITATION_SCHEME || "aip";

export const TRANSPORT_FIELD = `__${process.env.NEXT_PUBLIC_APP_SLUG || "platform"}Transport`;

export type Branding = {
  appName: string;
  tagline: string;
  description: string;
  logo: {
    favicon: string;
    heroAnimated: string;
    chatAvatar: string;
  };
  contact: {
    email: string;
    githubRepo: string;
  };
  theme: {
    primaryHsl: string;
    primaryForegroundHsl: string;
  };
  demo: {
    heroEyebrow: string;
    heroLineA: string;
    heroLineB: string;
    heroBody: string;
    ctaPrimary: string;
    ctaSecondary: string;
    chatHref: string;
    chatHrefSecondary: string;
    techHref: string;
    pillars: Array<{
      key: string;
      label: string;
      tagline: string;
      spec?: string;
    }>;
  };
};

/**
 * Empty string means "use the locale dictionary default". This keeps custom
 * deployment marketing copy possible without forcing English copy into a
 * Chinese deployment.
 */
export const BRAND_COPY_OVERRIDES = {
  heroEyebrow: process.env.NEXT_PUBLIC_BRAND_DEMO_HERO_EYEBROW || "",
  heroLineA: process.env.NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_A || "",
  heroLineB: process.env.NEXT_PUBLIC_BRAND_DEMO_HERO_LINE_B || "",
  heroBody: process.env.NEXT_PUBLIC_BRAND_DEMO_HERO_BODY || "",
  ctaPrimary: process.env.NEXT_PUBLIC_BRAND_DEMO_CTA_PRIMARY || "",
  ctaSecondary: process.env.NEXT_PUBLIC_BRAND_DEMO_CTA_SECONDARY || "",
};

export const BRANDING: Branding = {
  appName: process.env.NEXT_PUBLIC_BRAND_APP_NAME || "AI Protocol Platform",
  tagline: process.env.NEXT_PUBLIC_BRAND_TAGLINE || "Open Agent Protocol Platform",
  description:
    process.env.NEXT_PUBLIC_BRAND_DESCRIPTION ||
    "Self-hosted agent platform for Skills, AG-UI, A2UI, MCP and MCP Apps.",
  logo: {
    favicon:
      process.env.NEXT_PUBLIC_BRAND_FAVICON || "/images/logo/platform-mark.svg",
    heroAnimated:
      process.env.NEXT_PUBLIC_BRAND_LOGO_HERO || "/images/logo/platform-mark.svg",
    chatAvatar:
      process.env.NEXT_PUBLIC_BRAND_LOGO_AVATAR || "/images/logo/platform-mark.svg",
  },
  contact: {
    email: process.env.NEXT_PUBLIC_BRAND_EMAIL || "",
    githubRepo:
      process.env.NEXT_PUBLIC_BRAND_GITHUB ||
      "https://github.com/yuklcool/ai-protocol-platform",
  },
  theme: {
    primaryHsl: process.env.NEXT_PUBLIC_BRAND_PRIMARY_HSL || "234 57% 59%",
    primaryForegroundHsl:
      process.env.NEXT_PUBLIC_BRAND_PRIMARY_FOREGROUND_HSL || "210 40% 98%",
  },
  demo: {
    // Backwards-compatible values for components not yet migrated to useI18n.
    heroEyebrow: BRAND_COPY_OVERRIDES.heroEyebrow || "Open agent platform",
    heroLineA: BRAND_COPY_OVERRIDES.heroLineA || "Build AI agents",
    heroLineB: BRAND_COPY_OVERRIDES.heroLineB || "on open protocols",
    heroBody:
      BRAND_COPY_OVERRIDES.heroBody ||
      "Run Skills, AG-UI, A2UI and MCP Apps on a self-hosted platform.",
    ctaPrimary: BRAND_COPY_OVERRIDES.ctaPrimary || "Open the assistant",
    ctaSecondary: BRAND_COPY_OVERRIDES.ctaSecondary || "Explore skills",
    chatHref: process.env.NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF || "/",
    chatHrefSecondary:
      process.env.NEXT_PUBLIC_BRAND_DEMO_CHAT_HREF_SECONDARY || "/",
    techHref: process.env.NEXT_PUBLIC_BRAND_DEMO_TECH_HREF || "",
    // Keys stay stable so the i18n layer can translate the visible labels.
    pillars: [
      {
        key: "extract",
        label: "Skill orchestration",
        tagline: "Prompts, tools and runtime policy",
      },
      {
        key: "compare",
        label: "Model Providers",
        tagline: "Dynamic routing and capabilities",
      },
      {
        key: "benchmark",
        label: "Tenant isolation",
        tagline: "Server-authoritative boundaries",
      },
      {
        key: "compliance",
        label: "MCP integrations",
        tagline: "Tools, resources and Apps",
      },
      {
        key: "citation",
        label: "A2UI / AG-UI",
        tagline: "Structured interactive responses",
      },
      {
        key: "confidential",
        label: "Self-hosted",
        tagline: "Your infrastructure, your data",
      },
    ],
  },
};

/**
 * First-class extension seam for future tenant-level display branding. The
 * server remains authoritative for which overrides a tenant may supply; this
 * helper only defines the safe presentation fields a tenant may eventually
 * override without touching protocol/runtime identity.
 */
export type TenantBrandingOverrides = {
  appName?: string;
  tagline?: string;
  description?: string;
  logo?: Partial<Branding["logo"]>;
  theme?: Partial<Branding["theme"]>;
};

export function resolveBranding(
  overrides?: TenantBrandingOverrides | null,
): Branding {
  if (!overrides) return BRANDING;
  return {
    ...BRANDING,
    ...overrides,
    logo: { ...BRANDING.logo, ...overrides.logo },
    theme: { ...BRANDING.theme, ...overrides.theme },
    contact: BRANDING.contact,
    demo: BRANDING.demo,
  };
}
