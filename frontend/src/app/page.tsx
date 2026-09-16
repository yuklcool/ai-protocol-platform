import { BackendHealthBadge } from "@/components/BackendHealthBadge";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { MySkillsButton } from "@/components/MySkillsButton";
import { SignInButton } from "@/components/SignInButton";
import { HomeGate } from "@/components/home/HomeGate";
import {
  MarketplaceSkillsSection,
  type MarketplaceSkillSummary,
} from "@/components/home/MarketplaceSkillsSection";
import { AudienceBand } from "@/components/landing/AudienceBand";
import { Hero } from "@/components/landing/Hero";
import { OneHeroVisual } from "@/components/landing/OneHeroVisual";
import { ProtocolStripe } from "@/components/landing/ProtocolStripe";
import { BRANDING } from "@/lib/branding";

const SHOW_DEV_PROBES = process.env.NEXT_PUBLIC_SHOW_DEV_PROBES === "true";

async function getMarketplaceSkills(): Promise<MarketplaceSkillSummary[]> {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:1956";
    const res = await fetch(`${backendUrl}/api/skills/marketplace?limit=10`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const skills = await getMarketplaceSkills();

  return (
    <HomeGate>
      <main className="min-h-screen">
        <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 pt-4 md:px-10">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={BRANDING.logo.heroAnimated}
            alt={BRANDING.appName}
            className="h-8 w-8"
          />
          <div className="flex flex-wrap items-center justify-end gap-3">
            <LanguageSwitcher compact />
            <BackendHealthBadge />
            {SHOW_DEV_PROBES && <MySkillsButton />}
            <SignInButton />
          </div>
        </header>

        <Hero visual={<OneHeroVisual />} />
        <ProtocolStripe />
        <AudienceBand />
        <MarketplaceSkillsSection skills={skills} />
      </main>
    </HomeGate>
  );
}
