"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  DEFAULT_LOCALE,
  type Locale,
  normalizeLocale,
  translate,
  type TranslationKey,
  type TranslationParams,
} from "@/lib/i18n";

const STORAGE_KEY = "ai-protocol-platform.locale";

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, params?: TranslationParams) => string;
};

/**
 * Components are occasionally rendered outside the application provider in
 * unit tests, Storybook-like previews and embedders. Keep that path useful and
 * deterministic instead of throwing: isolated rendering falls back to English,
 * while the real application is always wrapped in I18nProvider and therefore
 * still defaults to DEFAULT_LOCALE (zh-CN for Self-host).
 */
const FALLBACK_CONTEXT: I18nContextValue = {
  locale: "en",
  setLocale: () => undefined,
  t: (key, params) => translate("en", key, params),
};

const I18nContext = createContext<I18nContextValue>(FALLBACK_CONTEXT);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    const stored = normalizeLocale(window.localStorage.getItem(STORAGE_KEY));
    if (stored) setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    window.localStorage.setItem(STORAGE_KEY, nextLocale);
    document.cookie = `aip_locale=${encodeURIComponent(nextLocale)}; Path=/; Max-Age=31536000; SameSite=Lax`;
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, params) => translate(locale, key, params),
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}
