"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useI18n } from "@/contexts/I18nContext";
import { completeOidcSignIn } from "@/lib/oidcAuth";

export default function OidcCallbackPage() {
  const { t, locale } = useI18n();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const complete = async () => {
      const params = new URLSearchParams(window.location.search);
      const providerError = params.get("error");
      const providerDescription = params.get("error_description");
      if (providerError) {
        setError(providerDescription || providerError);
        return;
      }

      const code = params.get("code");
      const state = params.get("state");
      if (!code || !state) {
        setError(t("auth.failed"));
        return;
      }

      try {
        const result = await completeOidcSignIn(code, state);
        if (!cancelled) window.location.replace(result.returnTo || "/");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("auth.failed"));
        }
      }
    };

    void complete();
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <main className="page-container flex min-h-screen items-center justify-center">
      <section className="glass-panel w-full max-w-md p-6 text-center">
        <h1 className="text-lg font-semibold text-foreground">{t("auth.signIn")}</h1>
        {error ? (
          <div className="notice notice--danger mt-3 flex-col text-left" role="alert">
            <p className="font-semibold">{t("auth.failed")}</p>
            <p className="break-words">{error}</p>
          </div>
        ) : (
          <p className="notice notice--info mt-3" role="status">{t("auth.checking")}</p>
        )}
        {error && <Link href="/" className="button-secondary mt-4">{locale.startsWith("zh") ? "返回首页重新登录" : "Return home to sign in"}</Link>}
      </section>
    </main>
  );
}
