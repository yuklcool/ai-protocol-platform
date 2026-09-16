"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { isLocalMode } from "@/lib/localMode";

export function LocalModeBanner() {
  const { t } = useI18n();
  const [disabledServices, setDisabledServices] = useState<string[]>([]);
  const [fetchError, setFetchError] = useState<boolean>(false);

  useEffect(() => {
    if (!isLocalMode()) return;
    fetch("/api/proxy/api/local-mode-status", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((body: { local_mode: boolean; disabled_services: string[] }) => {
        setDisabledServices(body.disabled_services ?? []);
      })
      .catch(() => setFetchError(true));
  }, []);

  if (!isLocalMode()) return null;

  return (
    <div
      role="status"
      aria-label={t("localMode.aria")}
      className="w-full bg-yellow-100 border-b border-yellow-300 text-yellow-900 text-xs px-4 py-2 flex items-center gap-4 flex-wrap"
    >
      <span className="font-medium">{t("localMode.summary")}</span>
      {disabledServices.length > 0 && !fetchError && (
        <span className="text-yellow-700 hidden md:inline">
          {t("localMode.disabled", { services: disabledServices.join(", ") })}
        </span>
      )}
      <a
        href="/workshop#graduating-from-local-mode"
        className="ml-auto underline hover:no-underline"
      >
        {t("localMode.connectGcp")}
      </a>
    </div>
  );
}
