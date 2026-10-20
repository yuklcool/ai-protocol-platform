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
    <section className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-8 md:py-16">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-base font-semibold">
          {t("home.audience.heading")}
        </h2>
      </div>
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {AUDIENCES.map((audience, i) => (
          <li
            key={audience.key}
            className="glass-panel glass-panel--flat relative flex min-w-0 flex-col gap-4 p-5 sm:p-6"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] tabular-nums text-primary">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="badge px-2.5 py-1 text-xs font-medium text-primary">
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
