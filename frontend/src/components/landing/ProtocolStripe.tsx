"use client";

import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import { BRANDING } from "@/lib/branding";
import type { TranslationKey } from "@/lib/i18n";
import { ProtocolIcon, type ProtocolIconKey } from "./ProtocolIcon";

const PILLAR_KEYS: Record<string, { label: TranslationKey; tagline: TranslationKey }> = {
  extract: {
    label: "home.pillar.extract.label",
    tagline: "home.pillar.extract.tagline",
  },
  compare: {
    label: "home.pillar.compare.label",
    tagline: "home.pillar.compare.tagline",
  },
  benchmark: {
    label: "home.pillar.benchmark.label",
    tagline: "home.pillar.benchmark.tagline",
  },
  compliance: {
    label: "home.pillar.compliance.label",
    tagline: "home.pillar.compliance.tagline",
  },
  citation: {
    label: "home.pillar.citation.label",
    tagline: "home.pillar.citation.tagline",
  },
  confidential: {
    label: "home.pillar.confidential.label",
    tagline: "home.pillar.confidential.tagline",
  },
};

export function ProtocolStripe() {
  const { t } = useI18n();
  const { demo } = BRANDING;
  const hasTechRoute = Boolean(demo.techHref);

  return (
    <section>
      <div className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-8 md:py-16">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-base font-semibold">
            {t("home.builtOn")}
          </h2>
          {hasTechRoute ? (
            <Link
              href={demo.techHref}
              className="button-ghost inline-flex items-center px-3 py-2 text-sm"
            >
              {t("home.seeFullStack")}
            </Link>
          ) : null}
        </div>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {demo.pillars.map((pillar) => {
            const translated = PILLAR_KEYS[pillar.key];
            const label = translated ? t(translated.label) : pillar.label;
            const tagline = translated ? t(translated.tagline) : pillar.tagline;
            const tileHref = hasTechRoute
              ? `${demo.techHref}#${pillar.key}`
              : pillar.spec ?? "#";
            const external = !hasTechRoute && Boolean(pillar.spec);
            return (
              <li key={pillar.key} className="glass-panel glass-panel--flat feature-card relative min-w-0">
                <Link
                  href={tileHref}
                  target={external ? "_blank" : undefined}
                  rel={external ? "noopener noreferrer" : undefined}
                  className="group flex h-full flex-col gap-3 rounded-[inherit] p-5 transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 sm:p-6"
                >
                  <ProtocolIcon
                    pillar={pillar.key as ProtocolIconKey}
                    className="h-8 w-8 rounded-xl bg-primary/10 p-1.5 text-primary"
                  />
                  <span className="text-sm font-semibold tracking-tight text-foreground">
                    {label}
                  </span>
                  <span className="text-sm leading-relaxed text-muted-foreground">
                    {tagline}
                  </span>
                </Link>
                {pillar.spec && hasTechRoute ? (
                  <a
                    href={pillar.spec}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="button-ghost absolute right-3 top-3 px-2 py-1 text-xs"
                    aria-label={t("home.specOpens", { label })}
                  >
                    {t("home.spec")}
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
