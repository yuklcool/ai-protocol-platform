"use client";

import { useI18n } from "@/contexts/I18nContext";
import { BRANDING } from "@/lib/branding";
import type { TranslationKey } from "@/lib/i18n";

const AUDIENCES: Array<{
  key: string;
  role: TranslationKey;
  headline: TranslationKey;
  body: TranslationKey;
}> = [
  {
    key: "operator",
    role: "home.audience.operator.role",
    headline: "home.audience.operator.headline",
    body: "home.audience.operator.body",
  },
  {
    key: "builder",
    role: "home.audience.builder.role",
    headline: "home.audience.builder.headline",
    body: "home.audience.builder.body",
  },
  {
    key: "engineer",
    role: "home.audience.engineer.role",
    headline: "home.audience.engineer.headline",
    body: "home.audience.engineer.body",
  },
];

export function AudienceBand() {
  const { t } = useI18n();

  return (
    <section className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10 md:py-20">
      <div className="mb-8 flex items-end justify-between">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          {t("home.audience.heading")}
        </h2>
      </div>
      <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3">
        {AUDIENCES.map((audience, i) => (
          <li
            key={audience.key}
            className="group relative flex flex-col gap-3 bg-background p-6"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] tabular-nums text-primary">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="inline-flex items-center rounded-full border border-primary/25 bg-primary/5 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-primary">
                {t(audience.role)}
              </span>
            </div>
            <h3 className="text-lg font-semibold leading-snug tracking-tight text-foreground">
              {t(audience.headline)}
            </h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t(audience.body, { appName: BRANDING.appName })}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
