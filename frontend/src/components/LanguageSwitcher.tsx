"use client";

import { useI18n } from "@/contexts/I18nContext";
import type { Locale } from "@/lib/i18n";

const OPTIONS: Array<{ value: Locale; key: "language.zhCN" | "language.en" }> = [
  { value: "zh-CN", key: "language.zhCN" },
  { value: "en", key: "language.en" },
];

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <label className="inline-flex items-center gap-2 text-xs text-muted-foreground">
      {!compact && <span>{t("language.label")}</span>}
      <select
        aria-label={t("language.label")}
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
        className="rounded-md border border-input bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {t(option.key)}
          </option>
        ))}
      </select>
    </label>
  );
}
