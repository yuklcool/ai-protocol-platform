// Presentational health bits for the tenant-admin overview (v6.9.x richer-UI
// quick-wins): a bucket-reachability dot + an at-a-glance config-health badge,
// both driven by the /api/admin/tenants/{domain}/validate response.
"use client";

import type { ReactNode } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { translateTenantAdmin } from "@/lib/i18n/tenantAdmin";
import type { TenantValidation, VerdictLevel } from "./tenantAdmin";

export type HealthState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; validation: TenantValidation };

export function bucketLevel(state?: HealthState): VerdictLevel | null {
  if (!state || state.kind !== "ready") return null;
  return state.validation.checks.find((c) => c.field === "documents_bucket")?.level ?? null;
}

export function healthSummary(validation: TenantValidation): { warnings: number; errors: number } {
  return {
    warnings: validation.checks.filter((c) => c.level === "warning").length,
    errors: validation.checks.filter((c) => c.level === "error").length,
  };
}

export function ReachDot({ state }: { state?: HealthState }) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateTenantAdmin>[1]) => translateTenantAdmin(locale, key);
  const loading = !state || state.kind === "loading";
  const level = bucketLevel(state);
  const { color, title } = loading
    ? { color: "bg-muted-foreground/40 animate-pulse", title: t("health.checkingReachability") }
    : level === "ok"
      ? { color: "bg-green-500", title: t("health.reachable") }
      : level === "warning"
        ? { color: "bg-amber-500", title: t("health.notReachable") }
        : level === "error"
          ? { color: "bg-red-500", title: t("health.probeError") }
          : { color: "bg-muted-foreground/40", title: t("health.notChecked") };
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`}
      title={title}
      aria-label={title}
    />
  );
}

export function HealthBadge({ state }: { state?: HealthState }) {
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateTenantAdmin>[1],
    params: Record<string, string | number> = {},
  ) => translateTenantAdmin(locale, key, params);
  if (!state || state.kind === "loading") {
    return <span className="text-xs text-muted-foreground">{t("health.checking")}</span>;
  }
  if (state.kind === "error") {
    return (
      <span className="text-xs text-muted-foreground" title={t("health.validateError")}>
        —
      </span>
    );
  }
  const { warnings, errors } = healthSummary(state.validation);
  if (!state.validation.ok || errors > 0) {
    return <HealthPill className="border-red-300 bg-red-50 text-red-700">{t("health.needsFix")}</HealthPill>;
  }
  if (warnings > 0) {
    return (
      <HealthPill className="border-amber-300 bg-amber-50 text-amber-700">
        {t(warnings === 1 ? "health.warning" : "health.warnings", { count: warnings })}
      </HealthPill>
    );
  }
  return <HealthPill className="border-green-300 bg-green-50 text-green-700">{t("health.healthy")}</HealthPill>;
}

function HealthPill({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${className}`}>
      {children}
    </span>
  );
}
