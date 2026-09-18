"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/contexts/I18nContext";
import { completeOidcSignIn } from "@/lib/oidcAuth";

export default function OidcCallbackPage() {
  const { t } = useI18n();
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
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="w-full max-w-md rounded-xl border border-border bg-card p-6 text-center shadow-sm">
        <h1 className="text-lg font-semibold text-foreground">{t("auth.signIn")}</h1>
        {error ? (
          <p className="mt-3 text-sm text-red-600" role="alert">
            {error}
          </p>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">{t("auth.checking")}</p>
        )}
      </section>
    </main>
  );
}
