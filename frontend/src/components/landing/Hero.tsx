"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { BRAND_COPY_OVERRIDES, BRANDING } from "@/lib/branding";

interface HeroProps {
  visual?: ReactNode;
}

export function Hero({ visual }: HeroProps) {
  const { t } = useI18n();
  const { demo } = BRANDING;
  const eyebrow = BRAND_COPY_OVERRIDES.heroEyebrow || t("home.hero.eyebrow");
  const lineA = BRAND_COPY_OVERRIDES.heroLineA || t("home.hero.lineA");
  const lineB = BRAND_COPY_OVERRIDES.heroLineB || t("home.hero.lineB");
  const body = BRAND_COPY_OVERRIDES.heroBody || t("home.hero.body");
  const primary = BRAND_COPY_OVERRIDES.ctaPrimary || t("home.hero.ctaPrimary");
  const secondary = BRAND_COPY_OVERRIDES.ctaSecondary || t("home.hero.ctaSecondary");

  return (
    <section className="relative mx-auto w-full max-w-7xl px-4 pb-12 pt-12 sm:px-8 md:pb-20 md:pt-20">
      <div
        className={
          visual
            ? "grid items-start gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16"
            : "flex flex-col items-start gap-8"
        }
      >
        <div className="flex flex-col gap-8">
          <Eyebrow text={eyebrow} />
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-foreground sm:text-4xl lg:text-5xl">
            {lineA}
            <br />
            <span className="text-gradient">{lineB}</span>
          </h1>
          <p className="max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            {body}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Link
              href={demo.chatHref}
              className="group inline-flex items-center gap-2 button-primary px-5 py-3 text-sm font-semibold transition-colors "
            >
              {primary}
              <ArrowIcon className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href={demo.chatHrefSecondary}
              className="inline-flex items-center gap-2 rounded-md border border-border px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-primary/50 hover:text-primary"
            >
              {secondary}
              <span aria-hidden className="text-muted-foreground">
                ↗
              </span>
            </Link>
          </div>
        </div>
        {visual ? <div>{visual}</div> : null}
      </div>
    </section>
  );
}

function Eyebrow({ text }: { text: string }) {
  return (
    <div className="inline-flex items-center gap-2 self-start rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
      </span>
      {text}
    </div>
  );
}

function ArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path
        d="M3 8h10M9 4l4 4-4 4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
